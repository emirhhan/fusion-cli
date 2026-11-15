"""Streamable HTTP MCP için OAuth 2.1/PKCE tarayıcı akışı."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import webbrowser
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx
from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata
from pydantic import AnyUrl

from ..config.models import McpServerConfig
from .oauth_flow import SerializedOAuth
from .oauth_page import callback_page
from .tokens import KeyringTokenStorage
from .types import McpConfigError

#: Loopback OAuth dönüşünün SABİT portu.
#
# Ölçülmüş engel: Facebook Login, yönlendirme adresinin uygulama ayarlarındaki
# kayıtla BİREBİR eşleşmesini ister. Dinleyici eskiden `port=0` ile açılıyordu ve
# adres her denemede `http://127.0.0.1:<rastgele>/oauth/callback` oluyordu; hiçbir
# zaman eşleşemezdi, yani kullanıcının KENDİ Meta uygulamasının client_id'siyle
# giriş yapması imkânsızdı. Dinamik kayıt (DCR) destekleyen sunucularda sabit port
# gerekmez; orada `port=0` davranışı korunur.
#
# Host da `localhost`tur: Facebook yönlendirme adresinde `localhost`u kabul eder ve
# kullanıcı panele bunu yazar. Dinleme yine yalnız loopback arayüzündedir.
DEFAULT_CALLBACK_PORT = 8765
#: Claude Code dönüş yolu (`http://localhost:PORT/callback`).
CALLBACK_PATH = "/callback"
#: Eski Fusion yolu; yalnız `client_id`'si olup dönüş portu verilmemiş eski kayıtlarda
#: kullanılır (sağlayıcıda `localhost:8765/oauth/callback` kayıtlı olabilir).
LEGACY_CALLBACK_PATH = "/oauth/callback"
CALLBACK_PORT_ENV = "MCP_OAUTH_CALLBACK_PORT"


#: `fusion mcp login --no-browser` bu bağlamda True yapar.
FORCE_NO_BROWSER: ContextVar[bool] = ContextVar("fusion_mcp_no_browser", default=False)


def use_paste_flow(environ: Mapping[str, str] | None = None) -> bool:
    """Tarayıcı yerine adres yapıştırma: `--no-browser` ya da SSH oturumu (etkileşimli tty)."""
    source = os.environ if environ is None else environ
    if not sys.stdin.isatty():
        return False
    return FORCE_NO_BROWSER.get() or bool(source.get("SSH_CONNECTION") or source.get("SSH_TTY"))


def _ask_pasted_redirect(url: str) -> str:
    print(f"Yetkilendirme adresi:\n{url}", file=sys.stderr)
    print("Tarayıcıda aç, sonra adres çubuğundaki dönüş adresini yapıştır:", file=sys.stderr)
    return sys.stdin.readline()


def callback_settings(
    config: McpServerConfig, environ: Mapping[str, str] | None = None
) -> tuple[int, str]:
    """(port, yol): `oauth.callbackPort` > `MCP_OAUTH_CALLBACK_PORT` > rastgele (#248).

    Eski kayıt (client_id var, port yok, ortam değişkeni yok) sağlayıcıda kayıtlı adresi
    bozmamak için `8765` + `/oauth/callback` ile kalır.
    """
    source = os.environ if environ is None else environ
    if config.oauth_callback_port is not None:
        return config.oauth_callback_port, CALLBACK_PATH
    raw = source.get(CALLBACK_PORT_ENV, "").strip()
    if raw.isdigit() and 0 < int(raw) < 65536:
        return int(raw), CALLBACK_PATH
    if config.client_id:
        return DEFAULT_CALLBACK_PORT, LEGACY_CALLBACK_PATH
    return 0, CALLBACK_PATH


def validate_remote_mcp_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return
    raise McpConfigError(
        "Uzak MCP adresi HTTPS olmalı; düz HTTP yalnız loopback için kullanılabilir."
    )


class McpLoginRequiredError(RuntimeError):
    """Sunucu giriş istiyor ama bu bağlamda giriş penceresi açılamaz."""


class McpBrowserOpenError(RuntimeError):
    """Giriş sayfası açılamadı (başsız/yapılandırılmamış tarayıcı); adres mesajdadır."""


#: SDK'nın OAuth akışındaki her hatayı yığın dökümüyle yazdığı logger.
_SDK_OAUTH_LOGGER = "mcp.client.auth.oauth2"


class _ExpectedLoginFilter(logging.Filter):
    """BEKLENEN "giriş gerekli" durumunun yığın dökümünü bastır.

    Ölçüldü (17 Eylül): girişi yapılmamış Notion için SDK her turda
    `logger.exception("OAuth flow error")` ile tam yığın dökümü basıyordu. Bu bir
    hata değil, kullanıcının henüz "Bağlan" demediği bir bağlantıdır; durum zaten
    `giris_gerekli` olarak arayüzde görünür. Diğer OAuth hataları olduğu gibi kalır.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        error = record.exc_info[1] if record.exc_info else None
        return not isinstance(error, McpLoginRequiredError)


def _silence_expected_login_errors() -> None:
    """Filtreyi SDK logger'ına bir kez ekle (tekrar çağrı etkisizdir)."""
    logger = logging.getLogger(_SDK_OAUTH_LOGGER)
    if not any(isinstance(item, _ExpectedLoginFilter) for item in logger.filters):
        logger.addFilter(_ExpectedLoginFilter())


class LoopbackOAuthCallback:
    """Tek OAuth dönüşü için yalnız loopback üzerinde yaşayan HTTP dinleyici."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 300,
        on_waiting: Callable[[bool], None] | None = None,
        port: int = DEFAULT_CALLBACK_PORT,
        interactive: bool = True,
        path: str = LEGACY_CALLBACK_PATH,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._port = port
        self._path = path
        #: Tarayıcı açılabilir mi? Tur yolunda AÇILAMAZ (bkz. `open_redirect`).
        self._interactive = interactive
        #: Kullanıcının tarayıcıda giriş yaptığı süreyi bildirir (True: başladı,
        #: False: bitti). Bağlantı süresi bu aralıkta işlememelidir.
        self._on_waiting = on_waiting
        self._server: asyncio.Server | None = None
        #: Yetkilendirme adresindeki `state`; dönüşte eşleşmeyen istek yok sayılır.
        self._expected_state: str | None = None
        self._result: asyncio.Future[tuple[str, str | None]] | None = None
        self.redirect_uri = f"http://localhost:{port}{path}" if port else ""

    async def start(self) -> None:
        if self._server is not None:
            return
        loop = asyncio.get_running_loop()
        self._result = loop.create_future()
        try:
            self._server = await asyncio.start_server(self._handle, "127.0.0.1", self._port)
        except OSError as error:
            # Sessizce başka bir porta kaymak, sağlayıcıda kayıtlı OLMAYAN bir
            # adresle giriş denemek olurdu; kullanıcı "neden eşleşmiyor" diye
            # bakarken hata hiç görünmezdi.
            raise OSError(
                f"OAuth dönüş portu {self._port} kullanılamıyor: {error}. "
                "Portu kullanan programı kapat ya da bağlantıda başka bir port seç."
            ) from error
        socket = self._server.sockets[0]
        port = int(socket.getsockname()[1])
        # Claude Code yönlendirmeyi `http://localhost:PORT/callback` biçiminde gönderir;
        # sabit port verilmemişse de aynı `localhost` biçimi (rastgele port) kullanılır.
        host = "localhost" if self._port or self._path == CALLBACK_PATH else "127.0.0.1"
        self.redirect_uri = f"http://{host}:{port}{self._path}"

    async def open_redirect(self, url: str) -> None:
        """Yetkilendirme sayfasını aç — YALNIZ kullanıcının açık eyleminde.

        Ölçüldü (11 Eylül): kullanıcı Fusion'a istek yazıp Enter'a bastığında
        Notion'un yetkilendirme sayfası açılıyordu. `notion` OAuth'lu bir uzak MCP
        ve her tur bağlanılıyor; token yoksa SDK buraya geliyor ve tarayıcı
        fırlıyordu. Giriş kullanıcının AÇIK eylemidir; tur yolunda bağlantı bir
        zenginleştirmedir ve sessizce atlanır.
        """
        if not self._interactive:
            raise McpLoginRequiredError(
                "Bu MCP sunucusu giriş istiyor. Bağlantılar ekranından 'Bağlan' de; "
                "tur sırasında giriş penceresi açılmaz."
            )
        await self.start()
        self._expected_state = parse_qs(urlparse(url).query).get("state", [None])[0]
        if use_paste_flow():
            # Claude Code `login --no-browser` / SSH: adres basılır, dönüş adresi yapıştırılır.
            self._accept_pasted(await asyncio.to_thread(_ask_pasted_redirect, url))
            return
        # Ölçüldü (30 Ekim): dönüş değeri yok sayılıyordu; tarayıcı açılamayınca
        # bağlantı süresi askıya alınıp 300 sn boşuna beklenir, adres görünmezdi.
        opened = await asyncio.to_thread(webbrowser.open, url, new=1, autoraise=True)
        if not opened:
            await self.close()
            logging.getLogger(__name__).warning("OAuth giriş sayfası açılamadı: %s", url)
            raise McpBrowserOpenError(
                "Tarayıcı açılamadı. Giriş adresini elle aç ve 'Bağlan'ı yeniden dene: " + url
            )
        if self._on_waiting is not None:
            self._on_waiting(True)

    def _accept_pasted(self, pasted: str) -> None:
        query = parse_qs(urlparse(pasted.strip()).query)
        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]
        if not code or state != self._expected_state:
            raise McpConfigError("Yapıştırılan dönüş adresi bu girişe ait değil (code/state yok).")
        self._set_result((code, state))

    async def wait_for_code(self) -> tuple[str, str | None]:
        if self._result is None:
            raise RuntimeError("OAuth callback dinleyicisi başlatılmadı.")
        try:
            return await asyncio.wait_for(self._result, timeout=self._timeout_seconds)
        finally:
            if self._on_waiting is not None:
                self._on_waiting(False)
            await self.close()

    async def close(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = (await reader.readline()).decode("ascii", errors="replace")
            parts = request_line.split(" ")
            target = parts[1] if len(parts) >= 2 else ""
            parsed = urlparse(target)
            query = parse_qs(parsed.query)
            state = query.get("state", [None])[0]
            error = query.get("error", [None])[0]
            code = query.get("code", [None])[0]
            if parsed.path != self._path or (not code and not error):
                # Ölçüldü (30 Ekim): her yabancı istek (başka sekme, ön-yükleyici, kötü
                # niyetli `fetch`) akışı düşürüyordu; sabit port tahmin edilebilir.
                status = "404 Not Found"
                page = callback_page(
                    ok=False, title="Geçersiz dönüş", message="Bu adres bir giriş dönüşü değil."
                )
            elif self._expected_state is not None and state != self._expected_state:
                status = "400 Bad Request"
                page = callback_page(
                    ok=False, title="Geçersiz dönüş", message="Bu dönüş bu girişe ait değil."
                )
            elif error:
                self._set_error(RuntimeError("OAuth girişi reddedildi veya iptal edildi."))
                status = "400 Bad Request"
                page = callback_page(
                    ok=False,
                    title="Bağlantı izni verilmedi",
                    message="Giriş reddedildi ya da iptal edildi; Fusion bağlanmadı.",
                )
            else:
                self._set_result((str(code), state))
                status = "200 OK"
                page = callback_page(
                    ok=True,
                    title="Bağlantı kuruldu",
                    message="Fusion izni aldı ve hesabına bağlandı.",
                )
            body = page.encode()
            headers = (
                f"HTTP/1.1 {status}\r\n"
                "Content-Type: text/html; charset=utf-8\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            ).encode()
            writer.write(headers + body)
            await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    def _set_result(self, value: tuple[str, str | None]) -> None:
        if self._result is not None and not self._result.done():
            self._result.set_result(value)

    def _set_error(self, error: Exception) -> None:
        if self._result is not None and not self._result.done():
            self._result.set_exception(error)


@dataclass(slots=True)
class OAuthBundle:
    auth: httpx.Auth
    callback: LoopbackOAuthCallback
    storage: KeyringTokenStorage


def registration_is_stale(
    client: OAuthClientInformationFull | None, redirect_uri: str, client_id: str = ""
) -> bool:
    """Saklanan istemci kaydı, ŞU ANKİ yönlendirme adresini kapsıyor mu?

    Kayıt, kaydedildiği adrese BAĞLIDIR. Ölçüldü (11 Eylül, Notion MCP): istemci
    daha önce rastgele portlu bir adresle kaydolmuştu; port sabitlendikten sonra
    yetkilendirme isteği yeni adresi gönderdi, sunucu kayıtlı adresi bekliyordu ve
    `Invalid redirect_uri for OAuth client` ile reddetti. Kullanıcının bunu kendi
    başına çözmesi mümkün değil: bayat kayıt anahtarlıkta, hata ekranda.

    Ayarlardaki `client_id` değiştiyse de kayıt bayattır (30 Ekim: eski kimlik
    kullanılmaya devam ediyordu). Ayarda `client_id` yoksa sunucunun verdiği korunur.

    Bayat kayıt SAKLANMAZ; atılır ve sunucuya yeniden kaydolunur.
    """
    if client is None:
        return False
    if client_id and client.client_id != client_id:
        return True
    # `redirect_uris` None olabilir: kayıt hiç adres taşımıyorsa eşleşme de yoktur.
    kayitli = {str(item).rstrip("/") for item in (client.redirect_uris or ())}
    return redirect_uri.rstrip("/") not in kayitli


async def oauth_provider_for(
    config: McpServerConfig,
    *,
    on_waiting: Callable[[bool], None] | None = None,
    interactive: bool = True,
) -> OAuthBundle:
    """Yapılandırma için SDK OAuth sağlayıcısı ve yaşam döngüsü kaynaklarını kur."""
    validate_remote_mcp_url(config.url)
    if not interactive:
        _silence_expected_login_errors()
    port, path = callback_settings(config)
    callback = LoopbackOAuthCallback(
        on_waiting=on_waiting, interactive=interactive, port=port, path=path
    )
    if not callback.redirect_uri:
        await callback.start()
    storage = KeyringTokenStorage(config.url)
    metadata = OAuthClientMetadata(
        redirect_uris=[AnyUrl(callback.redirect_uri)],
        token_endpoint_auth_method="none",
        scope=" ".join(config.scopes) or None,
        client_name="Fusion Desktop",
    )
    from .pool import mcp_oauth_flows

    lock = mcp_oauth_flows().lock_for(storage.debug_identity())
    async with lock:
        kayitli = await storage.get_client_info()
        if registration_is_stale(kayitli, callback.redirect_uri, config.client_id):
            await storage.clear()
            kayitli = None
        if config.client_id and kayitli is None:
            secret = await storage.get_client_secret()
            fields = metadata.model_dump()
            if secret:
                # Gizli istemci: sır token isteğinde gönderilir (Claude Code `--client-secret`).
                fields["token_endpoint_auth_method"] = "client_secret_post"
            await storage.set_client_info(
                OAuthClientInformationFull(
                    **fields, client_id=config.client_id, client_secret=secret or None
                )
            )

    def fresh_provider() -> httpx.Auth:
        return OAuthClientProvider(
            config.url,
            metadata,
            storage,
            redirect_handler=callback.open_redirect,
            callback_handler=callback.wait_for_code,
        )

    auth = SerializedOAuth(lock, fresh_provider)
    return OAuthBundle(auth=auth, callback=callback, storage=storage)

"""Streamable HTTP MCP için OAuth 2.1/PKCE tarayıcı akışı."""

from __future__ import annotations

import asyncio
import contextlib
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from mcp.client.auth import OAuthClientProvider
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata
from pydantic import AnyUrl

from ..config.models import McpServerConfig
from .tokens import KeyringTokenStorage

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


def validate_remote_mcp_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return
    raise ValueError("Uzak MCP adresi HTTPS olmalı; düz HTTP yalnız loopback için kullanılabilir.")


class McpLoginRequiredError(RuntimeError):
    """Sunucu giriş istiyor ama bu bağlamda giriş penceresi açılamaz."""


class LoopbackOAuthCallback:
    """Tek OAuth dönüşü için yalnız loopback üzerinde yaşayan HTTP dinleyici."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 300,
        on_waiting: Callable[[bool], None] | None = None,
        port: int = DEFAULT_CALLBACK_PORT,
        interactive: bool = True,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._port = port
        #: Tarayıcı açılabilir mi? Tur yolunda AÇILAMAZ (bkz. `open_redirect`).
        self._interactive = interactive
        #: Kullanıcının tarayıcıda giriş yaptığı süreyi bildirir (True: başladı,
        #: False: bitti). Bağlantı süresi bu aralıkta işlememelidir.
        self._on_waiting = on_waiting
        self._server: asyncio.Server | None = None
        self._result: asyncio.Future[tuple[str, str | None]] | None = None
        self.redirect_uri = ""

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
        host = "localhost" if self._port else "127.0.0.1"
        self.redirect_uri = f"http://{host}:{port}/oauth/callback"

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
        if self._on_waiting is not None:
            self._on_waiting(True)
        await asyncio.to_thread(webbrowser.open, url, new=1, autoraise=True)

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
            if parsed.path != "/oauth/callback" or (not code and not error):
                self._set_error(RuntimeError("Geçersiz OAuth callback isteği."))
                status, message = "400 Bad Request", "Geçersiz OAuth dönüşü."
            elif error:
                self._set_error(RuntimeError("OAuth girişi reddedildi veya iptal edildi."))
                status, message = "400 Bad Request", "Fusion bağlantı izni verilmedi."
            else:
                self._set_result((str(code), state))
                status, message = (
                    "200 OK",
                    "Fusion bağlantısı alındı. Bu pencereyi kapatabilirsiniz.",
                )
            body = f"<html><body><h1>Fusion</h1><p>{message}</p></body></html>".encode()
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
    auth: OAuthClientProvider
    callback: LoopbackOAuthCallback
    storage: KeyringTokenStorage


def registration_is_stale(client: OAuthClientInformationFull | None, redirect_uri: str) -> bool:
    """Saklanan istemci kaydı, ŞU ANKİ yönlendirme adresini kapsıyor mu?

    Kayıt, kaydedildiği adrese BAĞLIDIR. Ölçüldü (11 Eylül, Notion MCP): istemci
    daha önce rastgele portlu bir adresle kaydolmuştu; port sabitlendikten sonra
    yetkilendirme isteği yeni adresi gönderdi, sunucu kayıtlı adresi bekliyordu ve
    `Invalid redirect_uri for OAuth client` ile reddetti. Kullanıcının bunu kendi
    başına çözmesi mümkün değil: bayat kayıt anahtarlıkta, hata ekranda.

    Bayat kayıt SAKLANMAZ; atılır ve sunucuya yeniden kaydolunur.
    """
    if client is None:
        return False
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
    callback = LoopbackOAuthCallback(on_waiting=on_waiting, interactive=interactive)
    await callback.start()
    storage = KeyringTokenStorage(config.url)
    metadata = OAuthClientMetadata(
        redirect_uris=[AnyUrl(callback.redirect_uri)],
        token_endpoint_auth_method="none",
        scope=" ".join(config.scopes) or None,
        client_name="Fusion Desktop",
    )
    kayitli = await storage.get_client_info()
    if registration_is_stale(kayitli, callback.redirect_uri):
        # Token'lar da eski kayda aittir: yeni kayıtla birlikte yeniden alınmalı.
        await storage.clear()
        kayitli = None
    if config.client_id and kayitli is None:
        await storage.set_client_info(
            OAuthClientInformationFull(**metadata.model_dump(), client_id=config.client_id)
        )
    auth = OAuthClientProvider(
        config.url,
        metadata,
        storage,
        redirect_handler=callback.open_redirect,
        callback_handler=callback.wait_for_code,
    )
    return OAuthBundle(auth=auth, callback=callback, storage=storage)

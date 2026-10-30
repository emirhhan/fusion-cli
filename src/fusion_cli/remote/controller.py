"""Masaüstü yönetim yüzü: eşleştirme onayı, cihaz listesi, HTTP ve Telegram yaşam döngüsü.

`AppSession` yalnız `uzak.*` isteklerini buraya devreder. Uzaktan görevler ayrı bir
`AppSession` üzerinde (kendi sohbet/onay durumuyla) çalışır; masaüstü sohbeti karışmaz.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from ..accounts.workspaces import PERSONAL_WORKSPACE, bind_context, local_identity
from ..config.paths import active_account, user_data_dir
from ..core.atomic_file import atomic_replace_text
from ..core.protocols import Clock
from ..memory.run_store import SqliteRunStore
from .account_login import AccountLogin
from .asgi import RemoteApp
from .backend import AppSessionBackend
from .bind import BindPolicy, BindRefusedError, private_addresses, validate_bind
from .constants import DEFAULT_REMOTE_HOST, DEFAULT_REMOTE_PORT, HTTP_START_TIMEOUT_SECONDS
from .devices import CHANNEL_SIGNED, CHANNEL_TELEGRAM, Device, DeviceRegistry
from .mobile import MobileApi
from .navigation import NavigationHost
from .pairing import PairingError, PairingService
from .projects import ProjectStore
from .rate_limit import FailureLimiter
from .rpc import RemoteService
from .scopes import ELEVATED_SCOPES, parse_scopes
from .screen import MacScreenCapture
from .signing import SignatureVerifier
from .tasks import TaskStore
from .telegram import HttpTelegramApi, OffsetStore, TelegramBridge
from .uploads import MediaReader, UploadStore

TELEGRAM_TOKEN_NAME = "FUSION_TELEGRAM_BOT_TOKEN"


class _ServerStartError(RuntimeError):
    """uvicorn dinlemeye başlayamadan çıktı (çoğunlukla port kullanımda)."""


class TokenStore(Protocol):
    @property
    def available(self) -> bool: ...

    def get(self, env_name: str) -> str | None: ...
    def set(self, env_name: str, value: str) -> None: ...
    def delete(self, env_name: str) -> bool: ...


class WallClock:
    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()


#: Sunucunun kendiliğinden durması için tanınan süre; sonra zorla kapatılır.
SERVER_STOP_TIMEOUT_SECONDS = 5


def _expand(value: object) -> str:
    """Kullanıcının yazdığı dosya yolunu `~` açılmış metne çevir; boşsa boş metin."""
    return str(Path(str(value)).expanduser()) if value else ""


def _authenticate_account(identifier: str, password: str) -> str | None:
    """Doğrulanan hesabın kimliği (scrypt; parola saklanmaz/loglanmaz); başarısızsa None."""
    from ..accounts.store import SqliteAccountStore

    account = SqliteAccountStore().authenticate(identifier=identifier, password=password)
    return account.account_id if account is not None else None


def _fail(message: str) -> dict[str, Any]:
    return {"ok": False, "metin": message}


class RemoteController:
    """Uzak erişimin tek sahibi; ilk `uzak.*` çağrısında kurulur."""

    def __init__(
        self,
        *,
        home: Path,
        root: Path,
        secrets: TokenStore,
        session_factory: Callable[[Callable[[str], None]], Any],
        clock: Clock | None = None,
        navigation: NavigationHost | None = None,
    ) -> None:
        directory = home / "remote"
        self._clock = clock or WallClock()
        self._registry = DeviceRegistry(directory / "devices.json", self._clock)
        self._settings_path = directory / "settings.json"
        self._require_approval = self._load_require_approval()
        self._last_paired: dict[str, Any] | None = None
        self._pairing = PairingService(
            self._registry,
            self._clock,
            require_approval=lambda: self._require_approval,
            on_paired=self._remember_paired,
            account_id=active_account,
        )
        self._runs = SqliteRunStore(directory / "runs.sqlite3", clock=self._clock)
        self._store = TaskStore(self._runs)
        self._backend = AppSessionBackend(session_factory, root)
        self._projects = ProjectStore(directory / "projects.json")
        run_lock = asyncio.Lock()
        mobile = MobileApi(
            backend=self._backend,
            projects=self._projects,
            uploads=UploadStore(directory / "uploads", self._clock),
            media=MediaReader([home, user_data_dir(), root, directory / "uploads"]),
            clock=self._clock,
            default_root=root,
            session_lock=run_lock,
            navigation=navigation,
        )
        self._service = RemoteService(
            mobile=mobile,
            run_lock=run_lock,
            clock=self._clock,
            registry=self._registry,
            store=self._store,
            backend=self._backend,
            screen_capture=MacScreenCapture(),
            host_tenant=lambda: local_identity(active_account()).tenant_id,
        )
        self._directory = directory
        self._secrets = secrets
        self._server: Any = None
        self._server_task: asyncio.Task[None] | None = None
        self._telegram_task: asyncio.Task[None] | None = None
        self._telegram_api: HttpTelegramApi | None = None
        self._telegram_stop = asyncio.Event()
        self._telegram_error = ""
        self._address = ""
        self._port = DEFAULT_REMOTE_PORT

    async def dispatch(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "uzak.durum": self._status,
            "uzak.eslestir_baslat": self._pair_begin,
            "uzak.eslestir_onayla": self._pair_approve,
            "uzak.eslestir_reddet": self._pair_reject,
            "uzak.cihazlar": self._devices,
            "uzak.cihaz_iptal": self._revoke,
            "uzak.baslat": self._start_http,
            "uzak.durdur": self._stop_http,
            "uzak.telegram_baglan": self._telegram_connect,
            "uzak.telegram_kes": self._telegram_disconnect,
            "uzak.gorevler": self._tasks,
            "uzak.onay_cevapla": self._desktop_answer,
            "uzak.bekleyen": self._pending,
            "uzak.ekran_bekleyen": self._screen_pending,
            "uzak.ekran_onayla": self._screen_approve,
            "uzak.ekran_kes": self._screen_stop,
            "uzak.ekran_onizleme": self._screen_preview,
            "uzak.projeler_esitle": self._projects_sync,
            "uzak.ayar": self._set_setting,
        }
        handler = handlers.get(name)
        if handler is None:
            return _fail("Bilinmeyen uzak erişim isteği.")
        return await handler(data)

    async def _status(self, _data: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "dinliyor": self._server_task is not None and not self._server_task.done(),
            "adres": self._address,
            "telegram": self._telegram_task is not None and not self._telegram_task.done(),
            "telegramHata": self._telegram_error,
            "cihazSayisi": sum(1 for d in self._registry.list_devices() if not d.revoked),
            "port": self._port,
            "agAdresleri": private_addresses(),
            "onayIste": self._require_approval,
            "sonEslesen": self._last_paired,
        }

    def _load_require_approval(self) -> bool:
        """Kodla eşleştirmede masaüstü onayı iste (varsayılan kapalı)."""
        try:
            raw = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return isinstance(raw, dict) and raw.get("requireApproval") is True

    def _remember_paired(self, device: Device) -> None:
        """Masaüstü arayüzü bunu durum yoklamasında görüp "bağlandı" bildirimi gösterir."""
        self._last_paired = {
            "cihazId": device.device_id,
            "ad": device.name,
            "zaman": self._clock.now(),
        }

    async def _set_setting(self, data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data.get("onayIste"), bool):
            return _fail("Ayar değeri geçersiz.")
        self._require_approval = data["onayIste"]
        atomic_replace_text(
            self._settings_path, json.dumps({"requireApproval": self._require_approval})
        )
        return {"ok": True, "onayIste": self._require_approval}

    async def _pair_begin(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            scopes = parse_scopes(data.get("kapsamlar"))
        except ValueError as error:
            return _fail(str(error))
        channel = CHANNEL_TELEGRAM if data.get("kanal") == "telegram" else CHANNEL_SIGNED
        code, expires = self._pairing.begin(scopes, channel=channel)
        return {
            "ok": True,
            "kod": code,
            "bitis": expires,
            "kapsamlar": sorted(scopes),
            "yuksekYetki": sorted(scopes & ELEVATED_SCOPES),
        }

    async def _pair_approve(self, data: dict[str, Any]) -> dict[str, Any]:
        try:
            device = self._pairing.approve(str(data.get("kod", "")))
        except PairingError as error:
            return _fail(str(error))
        return {"ok": True, "cihaz": device.public_view()}

    async def _pair_reject(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": self._pairing.reject(str(data.get("kod", "")))}

    async def _devices(self, _data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "cihazlar": [d.public_view() for d in self._registry.list_devices()]}

    async def _revoke(self, data: dict[str, Any]) -> dict[str, Any]:
        device_id = str(data.get("cihazId", ""))
        self._service.stop_screen(device_id)
        return {"ok": self._registry.revoke(device_id)}

    async def _tasks(self, _data: dict[str, Any]) -> dict[str, Any]:
        # Masaüstü yalnız açık hesabın uzak görevlerini görür.
        owner = bind_context(local_identity(active_account()), PERSONAL_WORKSPACE)
        return {"ok": True, "gorevler": [t.view() for t in self._store.list_tasks(owner)]}

    async def _pending(self, _data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "sorular": self._service.pending_questions()}

    def _device_names(self, ids: list[str]) -> list[dict[str, str]]:
        names = {d.device_id: d.name for d in self._registry.list_devices()}
        return [{"cihazId": i, "ad": names.get(i, i)} for i in ids]

    async def _screen_pending(self, _data: dict[str, Any]) -> dict[str, Any]:
        gate = self._service.screen_gate
        return {
            "ok": True,
            "bekleyen": self._device_names(gate.pending()),
            "etkin": self._device_names(gate.active()),
        }

    async def _screen_approve(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": self._service.approve_screen(str(data.get("cihazId", "")))}

    async def _screen_stop(self, data: dict[str, Any]) -> dict[str, Any]:
        return {"ok": self._service.stop_screen(str(data.get("cihazId", "")))}

    async def _projects_sync(self, data: dict[str, Any]) -> dict[str, Any]:
        """Masaüstü proje kaydını (ad, klasör, sohbet eşlemesi) telefona görünür kılar."""
        self._projects.replace(data.get("projeler"), data.get("sohbetler"))
        return {"ok": True, "projeler": len(self._projects.list_projects())}

    async def _screen_preview(self, data: dict[str, Any]) -> dict[str, Any]:
        """Telefonun şu an izlediği kare; ek ekran yakalaması yapmaz."""
        latest = self._service.latest_screen_frame(str(data.get("cihazId", "")))
        if latest is None:
            return {"ok": False}
        sequence, frame, at = latest
        return {
            "ok": True,
            "seq": sequence,
            "at": at,
            "jpegBase64": base64.b64encode(frame).decode("ascii"),
        }

    async def _desktop_answer(self, data: dict[str, Any]) -> dict[str, Any]:
        accepted = await self._service.answer_from_desktop(
            str(data.get("soruId", "")), str(data.get("secim", ""))
        )
        return {"ok": accepted}

    async def _start_http(self, data: dict[str, Any]) -> dict[str, Any]:
        if self._server_task is not None and not self._server_task.done():
            return _fail("Uzak erişim zaten dinliyor.")
        host = str(data.get("adres", DEFAULT_REMOTE_HOST))
        try:
            port = int(data.get("port", DEFAULT_REMOTE_PORT))
        except (TypeError, ValueError):
            return _fail("Port bir sayı olmalı.")
        if not 1024 <= port <= 65535:
            return _fail("Port 1024–65535 arasında olmalı.")
        certificate, key = data.get("sertifika"), data.get("anahtar")
        if bool(certificate) != bool(key):
            return _fail("TLS için sertifika ve anahtar dosyası birlikte verilmeli.")
        certificate_path = _expand(certificate)
        key_path = _expand(key)
        for path in (certificate_path, key_path):
            if path and not await asyncio.to_thread(Path(path).is_file):
                return _fail(f"Dosya bulunamadı: {path}")
        policy = BindPolicy(
            allow_lan=data.get("yerelAg") is True,
            tls_enabled=bool(data.get("sertifika")),
            trusted_tunnel=data.get("guvenilirTunel") is True,
        )
        try:
            validate_bind(host, policy)
            import uvicorn
        except (BindRefusedError, ImportError) as error:
            return _fail(str(error))
        limiter = FailureLimiter(self._clock)
        # Hesapla giriş yalnız şifreli kanalda (TLS ya da güvenilir özel tünel) açılır.
        account_login = (
            AccountLogin(
                authenticate=_authenticate_account, registry=self._registry, limiter=limiter
            )
            if policy.tls_enabled or policy.trusted_tunnel
            else None
        )
        app = RemoteApp(
            service=self._service,
            registry=self._registry,
            pairing=self._pairing,
            verifier=SignatureVerifier(self._clock),
            limiter=limiter,
            account_login=account_login,
        )
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            ssl_certfile=certificate_path or None,
            ssl_keyfile=key_path or None,
        )
        self._server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._serve_guarded(self._server))
        failure = await self._wait_started(self._server, self._server_task)
        if failure is not None:
            self._server, self._server_task = None, None
            return _fail(f"Uzak erişim {host}:{port} üzerinde başlatılamadı: {failure}")
        scheme = "https" if data.get("sertifika") else "http"
        self._address = f"{scheme}://{host}:{port}"
        self._port = port
        return {"ok": True, "adres": self._address}

    async def _serve_guarded(self, server: Any) -> None:  # noqa: ANN401
        """`serve()` bind hatasında `sys.exit(1)` atar; SystemExit görevden olay döngüsüne
        yayılıp sidecar'ı düşürmesin diye burada yakalanır."""
        try:
            await server.serve()
        except SystemExit as error:
            raise _ServerStartError(f"çıkış kodu {error.code}") from None

    async def _wait_started(self, server: Any, task: asyncio.Task[None]) -> str | None:  # noqa: ANN401
        """Sunucu dinlemeye başlayana dek bekle; başlayamazsa nedeni döner.

        Adres `ok:true` ile hemen dönerse port doluyken kullanıcı hatayı hiç görmezdi.
        """
        deadline = asyncio.get_running_loop().time() + HTTP_START_TIMEOUT_SECONDS
        while not server.started:
            if task.done():
                error = task.exception() if not task.cancelled() else None
                return f"port kullanımda olabilir ({error})" if error else "sunucu kapandı"
            if asyncio.get_running_loop().time() > deadline:
                server.should_exit = True
                return "zaman aşımı"
            await asyncio.sleep(0.02)
        return None

    async def _stop_http(self, _data: dict[str, Any]) -> dict[str, Any]:
        await self._stop_server()
        return {"ok": True}

    async def _stop_server(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._server_task is not None:
            # `wait` görevi iptal ETMEZ; wait_for iptal edip bitmesini beklerdi, inatçıda takılırdı.
            done, _pending = await asyncio.wait(
                {self._server_task}, timeout=SERVER_STOP_TIMEOUT_SECONDS
            )
            if not done:
                # Nazik durma olmadı (açık bağlantılar): zorla kapat, yoksa port bağlı kalır.
                if self._server is not None:
                    self._server.force_exit = True
                self._server_task.cancel()
                await asyncio.wait({self._server_task}, timeout=SERVER_STOP_TIMEOUT_SECONDS)
            elif not self._server_task.cancelled():
                self._server_task.exception()  # görevin kendi hatası okunur (uyarı çıkmasın)
        self._server, self._server_task, self._address = None, None, ""

    async def _telegram_connect(self, data: dict[str, Any]) -> dict[str, Any]:
        token = data.get("belirtec")
        if isinstance(token, str) and token.strip():
            if not self._secrets.available:
                return _fail("Sistem anahtarlığı kullanılamıyor; belirteç saklanamadı.")
            self._secrets.set(TELEGRAM_TOKEN_NAME, token.strip())
        stored = self._secrets.get(TELEGRAM_TOKEN_NAME) if self._secrets.available else None
        if not stored:
            return _fail("Telegram bot belirteci gerekli.")
        await self._stop_telegram()
        self._telegram_stop = asyncio.Event()
        self._telegram_api = HttpTelegramApi(stored)
        bridge = TelegramBridge(
            api=self._telegram_api,
            service=self._service,
            registry=self._registry,
            pairing=self._pairing,
            store=self._store,
            clock=self._clock,
            offsets=OffsetStore(self._directory / "telegram_offset.json"),
        )
        self._telegram_task = asyncio.create_task(
            bridge.run(self._telegram_stop, self._remember_error)
        )
        return {"ok": True}

    async def _remember_error(self, message: str) -> None:
        self._telegram_error = message

    async def _telegram_disconnect(self, _data: dict[str, Any]) -> dict[str, Any]:
        await self._stop_telegram()
        if self._secrets.available:
            self._secrets.delete(TELEGRAM_TOKEN_NAME)
        for device in self._registry.list_devices():
            if device.channel == CHANNEL_TELEGRAM:
                self._registry.revoke(device.device_id)
        return {"ok": True}

    async def _stop_telegram(self) -> None:
        self._telegram_stop.set()
        if self._telegram_task is not None:
            self._telegram_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._telegram_task
        self._telegram_task = None
        if self._telegram_api is not None:
            with contextlib.suppress(Exception):
                await self._telegram_api.aclose()  # httpx istemcisi sızmasın
            self._telegram_api = None

    async def aclose(self) -> None:
        await self._stop_server()
        await self._stop_telegram()
        await self._service.aclose()
        self._runs.close()

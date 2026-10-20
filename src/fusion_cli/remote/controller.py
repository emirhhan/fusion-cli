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

from ..config.paths import user_data_dir
from ..core.protocols import Clock
from .account_login import AccountLogin
from .asgi import RemoteApp
from .backend import AppSessionBackend
from .bind import BindPolicy, BindRefusedError, private_addresses, validate_bind
from .constants import DEFAULT_REMOTE_HOST, DEFAULT_REMOTE_PORT
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


def _expand(value: object) -> str:
    """Kullanıcının yazdığı dosya yolunu `~` açılmış metne çevir; boşsa boş metin."""
    return str(Path(str(value)).expanduser()) if value else ""


def _authenticate_account(identifier: str, password: str) -> bool:
    """Fusion hesap deposunda kimlik + parola doğrulaması (scrypt; parola saklanmaz/loglanmaz)."""
    from ..accounts.store import SqliteAccountStore

    return SqliteAccountStore().authenticate(identifier=identifier, password=password) is not None


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
        )
        self._store = TaskStore(self._clock)
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
        )
        self._directory = directory
        self._secrets = secrets
        self._server: Any = None
        self._server_task: asyncio.Task[None] | None = None
        self._telegram_task: asyncio.Task[None] | None = None
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
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps({"requireApproval": self._require_approval}), encoding="utf-8"
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
        return {"ok": True, "gorevler": [t.view() for t in self._store.list_tasks()]}

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
        self._server_task = asyncio.create_task(self._server.serve())
        scheme = "https" if data.get("sertifika") else "http"
        self._address = f"{scheme}://{host}:{port}"
        self._port = port
        return {"ok": True, "adres": self._address}

    async def _stop_http(self, _data: dict[str, Any]) -> dict[str, Any]:
        await self._stop_server()
        return {"ok": True}

    async def _stop_server(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._server_task is not None:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._server_task, timeout=5)
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
        bridge = TelegramBridge(
            api=HttpTelegramApi(stored),
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

    async def aclose(self) -> None:
        await self._stop_server()
        await self._stop_telegram()
        await self._service.aclose()

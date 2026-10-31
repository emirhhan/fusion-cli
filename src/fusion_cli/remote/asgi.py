"""HTTP/ASGI yüzeyi: eşleştirme uçları, imzalı RPC ve herkese açık statik PWA dosyaları.

Bu katman yalnız kimlik doğrular ve yönlendirir; iş mantığı `RemoteService`dedir.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
from pathlib import Path
from typing import Any

from .account_login import AccountLogin, LoginError
from .constants import BODY_READ_TIMEOUT_SECONDS, MAX_BODY_BYTES, RPC_VERSION
from .devices import CHANNEL_SIGNED, DeviceRegistry
from .pairing import PairingError, PairingService
from .rate_limit import FailureLimiter
from .rpc import RemoteService
from .signing import SignatureVerifier, SignedRequest

PWA_DIRECTORY = Path(__file__).parent / "pwa"
_LOG = logging.getLogger(__name__)
_JS = "text/javascript; charset=utf-8"
_PNG = "image/png"
_STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
    "/icon-192.png": ("icon-192.png", _PNG),
    "/icon-512.png": ("icon-512.png", _PNG),
    "/apple-touch-icon.png": ("apple-touch-icon.png", _PNG),
    **{
        f"/{name}.js": (f"{name}.js", _JS)
        for name in (
            "app",
            "api",
            "approvals",
            "chat",
            "dom",
            "media",
            "pair-link",
            "screen-stream",
            "screen-view",
            "dock",
            "signing",
            "store",
            "sw",
            "views-chats",
            "views-settings",
            "views-tasks",
            "voice",
        )
    },
}
_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),
    (
        b"content-security-policy",
        b"default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; "
        b"style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'",
    ),
]


class RemoteApp:
    """ASGI uygulaması; kimlik doğrulama burada, yetki `RemoteService`te."""

    def __init__(
        self,
        *,
        service: RemoteService,
        registry: DeviceRegistry,
        pairing: PairingService,
        verifier: SignatureVerifier,
        limiter: FailureLimiter,
        account_login: AccountLogin | None = None,
    ) -> None:
        self._account_login = account_login
        self._service = service
        self._registry = registry
        self._pairing = pairing
        self._verifier = verifier
        self._limiter = limiter

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:  # noqa: ANN401
        if scope["type"] == "lifespan":
            await _lifespan(receive, send)
            return
        if scope["type"] != "http":
            # websocket vb. desteklenmez: sessizce dönmek uvicorn'da uyarı üretiyordu (R1-36).
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        method, path = scope["method"], scope["path"]
        client = _client_identity(scope)
        if method == "GET" and path in _STATIC:
            await self._static(send, path)
            return
        if method != "POST":
            await self._json(send, 405, {"error": "yontem_izinsiz"})
            return
        try:
            body = await asyncio.wait_for(_read_body(receive), BODY_READ_TIMEOUT_SECONDS)
        except TimeoutError:
            await self._json(send, 408, {"error": "govde_zaman_asimi"})
            return
        if body is None:
            await self._json(send, 413, {"error": "govde_buyuk"})
            return
        if path == f"/{RPC_VERSION}/pair/submit":
            await self._pair_submit(send, client, body)
        elif path == f"/{RPC_VERSION}/pair/claim":
            await self._pair_claim(send, client, body)
        elif path == f"/{RPC_VERSION}/auth/options":
            await self._json(send, 200, {"accountLogin": self._account_login is not None})
        elif path == f"/{RPC_VERSION}/auth/login":
            await self._auth_login(send, client, body)
        elif path == f"/{RPC_VERSION}/rpc":
            await self._rpc(scope, send, client, body)
        else:
            await self._json(send, 404, {"error": "bulunamadi"})

    async def _pair_submit(self, send: Any, client: str, body: bytes) -> None:  # noqa: ANN401
        if self._limiter.is_locked(f"pair:{client}"):
            await self._json(send, 429, {"error": "cok_deneme"})
            return
        payload = _parse(body)
        try:
            scopes = self._pairing.submit(
                str(payload.get("code", "")),
                str(payload.get("deviceName", "")),
                channel=CHANNEL_SIGNED,
                claim_key=str(payload.get("claimKey", ""))[:128],
            )
        except PairingError as error:
            self._limiter.record_failure(f"pair:{client}")
            await self._json(send, 400, {"error": "eslestirme", "message": str(error)})
            return
        state = (
            "onaylandi"
            if self._pairing.is_approved(str(payload.get("code", "")))
            else "onay_bekliyor"
        )
        await self._json(send, 200, {"scopes": sorted(scopes), "state": state})

    async def _pair_claim(self, send: Any, client: str, body: bytes) -> None:  # noqa: ANN401
        if self._limiter.is_locked(f"pair:{client}"):
            await self._json(send, 429, {"error": "cok_deneme"})
            return
        payload = _parse(body)
        try:
            device = self._pairing.claim(
                str(payload.get("code", "")), str(payload.get("claimKey", ""))[:128]
            )
        except PairingError as error:
            self._limiter.record_failure(f"pair:{client}")
            await self._json(send, 400, {"error": "eslestirme", "message": str(error)})
            return
        if device is None:
            await self._json(send, 200, {"state": "onay_bekliyor"})
            return
        await self._json(
            send,
            200,
            {
                "state": "onaylandi",
                "deviceId": device.device_id,
                "secret": device.secret_hex,
                "scopes": sorted(device.scopes),
            },
        )

    async def _auth_login(self, send: Any, client: str, body: bytes) -> None:  # noqa: ANN401
        if self._account_login is None:
            await self._json(send, 403, {"error": "hesap_girisi_kapali"})
            return
        payload = _parse(body)
        try:
            device = await self._account_login.login(
                client,
                str(payload.get("identifier", "")),
                str(payload.get("password", "")),
                str(payload.get("deviceName", "")),
            )
        except LoginError as error:
            await self._json(send, error.status, {"error": error.code, "message": error.message})
            return
        await self._json(
            send,
            200,
            {
                "state": "onaylandi",
                "deviceId": device.device_id,
                "secret": device.secret_hex,
                "scopes": sorted(device.scopes),
            },
        )

    async def _rpc(self, scope: dict[str, Any], send: Any, client: str, body: bytes) -> None:  # noqa: ANN401
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        device_id = headers.get("x-fusion-device", "")
        key = f"rpc:{client}:{device_id}"
        if self._limiter.is_locked(key):
            await self._json(send, 429, {"error": "cok_deneme"})
            return
        device = self._registry.active(device_id)
        signed = _signed_request(scope, headers, body)
        verdict = (
            self._verifier.verify(device_id, device.secret, signed)
            if device is not None and signed is not None
            else None
        )
        if device is None or verdict is None or not verdict.ok:
            reason = "cihaz_iptal" if device is None else (verdict.reason if verdict else "imza")
            # İmza geçerliyken gelen sıra/saat/nonce hataları gerçek cihazın geçici sapmasıdır:
            # kilit sayacına yazılmaz (aksi halde eşzamanlı isteklerde cihaz kendini kilitler).
            if reason not in {"sira_eski", "nonce_tekrar", "zaman_asimi"}:
                self._limiter.record_failure(key)
            # İstemci yalnız `cihaz_iptal`de eşleşmeyi siler; diğer nedenler yeniden denenir.
            await self._json(send, 401, {"error": "kimlik_dogrulanamadi", "reason": reason})
            return
        self._limiter.record_success(key)
        # İlk imzalı istek, eşleştirme sırrının telefona ulaştığının kanıtıdır.
        self._pairing.acknowledge(device.device_id)
        request = _parse(body)
        method, params = request.get("method"), request.get("params")
        if not isinstance(method, str):
            await self._json(send, 400, {"error": "gecersiz_istek"})
            return
        try:
            result = await self._service.call(
                device, method, params if isinstance(params, dict) else {}
            )
        except Exception:  # işlenmemiş istisna bağlantıyı yarım bırakmasın; ayrıntı günlükte
            _LOG.exception("Uzak RPC işlenemedi: %s", method)
            await self._json(send, 500, {"error": "sunucu_hatasi"})
            return
        await self._json(send, 200, result.view())

    async def _static(self, send: Any, path: str) -> None:  # noqa: ANN401
        name, content_type = _STATIC[path]
        file = PWA_DIRECTORY / name
        if not file.is_file():
            await self._json(send, 404, {"error": "bulunamadi"})
            return
        await self._respond(send, 200, file.read_bytes(), content_type)

    async def _json(self, send: Any, status: int, payload: dict[str, Any]) -> None:  # noqa: ANN401
        await self._respond(
            send, status, json.dumps(payload, ensure_ascii=False).encode(), "application/json"
        )

    @staticmethod
    async def _respond(send: Any, status: int, body: bytes, content_type: str) -> None:  # noqa: ANN401
        headers = [(b"content-type", content_type.encode()), *_SECURITY_HEADERS]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


async def _lifespan(receive: Any, send: Any) -> None:  # noqa: ANN401
    """Uvicorn yaşam döngüsü iletilerine yanıt verir; başlatma/kapatma işi yoktur."""
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


def _client_identity(scope: dict[str, Any]) -> str:
    """Hız sınırı için istemci kimliği.

    Güvenilir tünel/Tailscale proxy'si (`tailscale serve`) loopback'ten bağlanır; eş adresi
    hep 127.0.0.1 olunca bütün dünya aynı kilit anahtarını paylaşır (R1-11). Eş loopback ise
    proxy'nin eklediği `X-Forwarded-For` zincirinin SON girdisi kullanılır (ilk girdi
    istemci tarafından sahtelenebilir). Loopback olmayan eşte başlık yok sayılır.
    """
    peer = str((scope.get("client") or ("?", 0))[0])
    try:
        if not ipaddress.ip_address(peer).is_loopback:
            return peer
    except ValueError:
        return peer
    for name, value in scope.get("headers", []):
        if name.lower() == b"x-forwarded-for":
            last = value.decode("latin-1").split(",")[-1].strip()
            try:
                return str(ipaddress.ip_address(last))
            except ValueError:
                return peer
    return peer


async def _read_body(receive: Any) -> bytes | None:  # noqa: ANN401
    chunks: list[bytes] = []
    size = 0
    while True:
        message = await receive()
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            return None
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


def _parse(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body or b"{}")
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _signed_request(
    scope: dict[str, Any], headers: dict[str, str], body: bytes
) -> SignedRequest | None:
    try:
        return SignedRequest(
            method=scope["method"],
            path=scope["path"],
            timestamp=int(headers["x-fusion-ts"]),
            nonce=headers["x-fusion-nonce"],
            sequence=int(headers["x-fusion-seq"]),
            body=body,
            signature=headers["x-fusion-sig"],
        )
    except (KeyError, ValueError):
        return None

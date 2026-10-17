"""Uçtan uca PWA sınaması için gerçek ASGI uygulaması (servis, imza, eşleştirme, hesap girişi).

Yalnız yürütücü (ajan) ve ekran yakalama sahtedir. Kontrol uçları (`/__*`) sınama içindir:
`/__code` yeni eşleştirme kodu üretir, `/__approve` bekleyen ekran isteğini onaylar.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import uvicorn
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fusion_cli.remote.account_login import AccountLogin
from fusion_cli.remote.asgi import RemoteApp
from fusion_cli.remote.devices import DeviceRegistry
from fusion_cli.remote.mobile import MobileApi
from fusion_cli.remote.pairing import PairingService
from fusion_cli.remote.projects import ProjectStore
from fusion_cli.remote.rate_limit import FailureLimiter
from fusion_cli.remote.rpc import RemoteService
from fusion_cli.remote.signing import SignatureVerifier
from fusion_cli.remote.tasks import TaskStore
from fusion_cli.remote.uploads import MediaReader, UploadStore


class Clock:
    def now(self) -> float:
        return time.time()

    def monotonic(self) -> float:
        return time.monotonic()


def _jpeg() -> bytes:
    image = Image.new("RGB", (1280, 800), (30, 40, 70))
    draw = ImageDraw.Draw(image)
    for x in range(0, 1280, 80):
        draw.line([(x, 0), (x, 800)], fill=(70, 80, 120))
    draw.rectangle([40, 40, 1240, 90], fill=(200, 200, 210))
    draw.ellipse([500, 300, 780, 580], outline=(255, 120, 80), width=12)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG")
    return buffer.getvalue()


class Capture:
    async def frame(self) -> bytes:
        return _jpeg()


PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class Navigation:
    """Sahte dock: birkaç uygulama, çok pencereli Chrome ve uzun sekme listesi."""

    focused: dict[str, object] | None = None

    async def list(self) -> dict[str, object]:
        windows = [
            {
                "kind": "window",
                "id": 10,
                "pid": 100,
                "app": "Google Chrome",
                "title": "Fusion",
                "icon": PNG,
                "visible": True,
            },
            {
                "kind": "window",
                "id": 11,
                "pid": 100,
                "app": "Google Chrome",
                "title": "Gizli pencere",
                "visible": False,
            },
            {
                "kind": "window",
                "id": 20,
                "pid": 200,
                "app": "Finder",
                "title": "Masaüstü",
                "visible": False,
            },
            {
                "kind": "window",
                "id": 30,
                "pid": 300,
                "app": "Slack",
                "title": "genel",
                "visible": False,
            },
            {
                "kind": "window",
                "id": 31,
                "pid": 301,
                "app": "Slack",
                "title": "ekip",
                "visible": False,
            },
        ]
        tabs = [
            {
                "kind": "tab",
                "id": i,
                "windowId": 5 if i < 9 else 6,
                "title": f"Sayfa {i}",
                "url": f"https://site{i}.example.com/",
                "active": i == 2,
            }
            for i in range(1, 13)
        ]
        return {
            "ok": True,
            "windows": windows,
            "tabs": tabs,
            "native_error": "",
            "chrome_error": "",
        }

    async def focus(self, target: dict[str, object]) -> dict[str, object]:
        Navigation.focused = target
        return {"ok": True}


class Backend:
    """Sahte ajan: akan yanıt, onay sorusu, iptal; oturum istekleri betikli."""

    def __init__(self) -> None:
        self.options: dict[str, dict[str, Any]] = {}
        self.answered: dict[str, asyncio.Event] = {}
        self.cancelled: set[str] = set()
        self.history: dict[str, list[dict[str, str]]] = {
            "c1": [
                {"rol": "kullanici", "metin": "Ürün sayfasında fiyat nasıl görünsün?"},
                {
                    "rol": "asistan",
                    "metin": "Fiyatı başlığın altına koy, indirimi üstü çizili göster.",
                },
            ]
        }
        self._chat = ""

    def prepare_run(self, run_id: str, options: dict[str, Any]) -> None:
        self.options[run_id] = options

    async def start(self, run_id: str, prompt: str, sink: Any) -> None:
        sink("started", {})
        if "onay" in prompt:
            event = self.answered.setdefault(run_id, asyncio.Event())
            sink(
                "question",
                {
                    "questionId": f"q-{run_id}",
                    "tur": "onay",
                    "arac": "web_search",
                    "baslik": "Web'de aranacak: fiyat",
                    "hedef": "fiyat karşılaştırma",
                    "secenekler": [{"deger": "once"}, {"deger": "deny"}],
                },
            )
            await event.wait()
        for part in ("Merhaba, ", "bakıyorum… ", "Bitti."):
            if run_id in self.cancelled:
                sink("failed", {"summary": "Görev durduruldu."})
                return
            sink("event", {"olay": "TokenReceived", "text": part, "provisional": False})
            await asyncio.sleep(0.6 if "uzun" in prompt else 0.05)
        if "uzun" in prompt:
            for _ in range(60):
                if run_id in self.cancelled:
                    break
                await asyncio.sleep(0.2)
        sink("done", {"summary": "Merhaba, bakıyorum… Bitti."})

    async def cancel(self, run_id: str) -> bool:
        self.cancelled.add(run_id)
        return True

    async def answer(self, question_id: str, answer: dict[str, Any]) -> bool:
        self.answered.setdefault(question_id.removeprefix("q-"), asyncio.Event()).set()
        return True

    def pause_supported(self) -> bool:
        return False

    def kits(self) -> list[dict[str, Any]]:
        return []

    async def call(self, name: str, data: dict[str, Any]) -> dict[str, Any]:
        if name == "oturum.baslat" and data.get("sohbet_id"):
            self._chat = str(data["sohbet_id"])
        scripted: dict[str, dict[str, Any]] = {
            "sohbet.listele": {
                "ok": True,
                "sohbetler": [
                    {
                        "sohbet_id": "c1",
                        "baslik": "Ürün sayfası düzeni",
                        "guncelleme": time.time() - 300,
                        "mesaj_sayisi": 2,
                    },
                    {
                        "sohbet_id": "c2",
                        "baslik": "Kargo hesabı",
                        "guncelleme": time.time() - 86400,
                        "mesaj_sayisi": 2,
                    },
                ],
            },
            "oturum.gecmis": {"ok": True, "mesajlar": self.history.get(self._chat, [])},
            "kademe.listele": {
                "ok": True,
                "kademeler": [
                    {"ad": "hizli", "etiket": "Hızlı", "model": "nim/llama"},
                    {"ad": "guclu", "etiket": "Güçlü", "model": "nim/405b"},
                ],
                "etkin": "hizli",
                "duzenlenebilir": True,
            },
            "kademe.sec": {"ok": True, "metin": "Model seçildi."},
            "zamanlama.liste": {
                "ok": True,
                "gorevler": [
                    {
                        "id": "z1",
                        "baslik": "Sabah stok raporu",
                        "gorev": "stok raporunu çıkar",
                        "kok": "/x",
                        "etkin": True,
                        "sonraki": time.time() + 3600,
                        "tur": "gunluk",
                    }
                ],
            },
            "zamanlama.etkin": {"ok": True},
        }
        return scripted.get(name, {"ok": True})


async def main(port: int) -> None:
    clock = Clock()
    tmp = Path(tempfile.mkdtemp(prefix="fusion-e2e-"))
    registry = DeviceRegistry(tmp / "d.json", clock)
    pairing = PairingService(registry, clock, require_approval=lambda: False)
    backend = Backend()
    lock = asyncio.Lock()
    mobile = MobileApi(
        backend=backend,
        projects=ProjectStore(tmp / "p.json"),
        uploads=UploadStore(tmp / "u", clock),
        media=MediaReader([tmp]),
        clock=clock,
        default_root=tmp,
        session_lock=lock,
        navigation=Navigation(),
    )
    service = RemoteService(
        clock=clock,
        registry=registry,
        store=TaskStore(clock),
        backend=backend,
        screen_capture=Capture(),
        mobile=mobile,
        run_lock=lock,
    )
    limiter = FailureLimiter(clock)
    login = AccountLogin(
        authenticate=lambda i, p: (i, p) == ("emir", "parola123"),
        registry=registry,
        limiter=limiter,
    )
    inner = RemoteApp(
        service=service,
        registry=registry,
        pairing=pairing,
        verifier=SignatureVerifier(clock),
        limiter=limiter,
        account_login=login,
    )

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["path"] == "/__focused":
            body = json.dumps(Navigation.focused).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        if scope["type"] == "http" and scope["path"] == "/__code":
            code, _ = pairing.begin(
                ["project.read", "agent.run", "agent.cancel", "desktop.observe"]
            )
            body = json.dumps({"code": code}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await inner(scope, receive, send)

    print("HAZIR", flush=True)
    await uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    ).serve()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1])))

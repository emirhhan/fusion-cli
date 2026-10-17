"""Telegram köprüsü: eşleştirme, DM-only, tekrar önleme, sır reddi, step-up bildirimi."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from fusion_cli.remote.devices import CHANNEL_TELEGRAM, DeviceRegistry
from fusion_cli.remote.pairing import PairingService
from fusion_cli.remote.rpc import RemoteService
from fusion_cli.remote.tasks import TaskStore
from fusion_cli.remote.telegram import OffsetStore, TelegramBridge
from tests.test_remote_service import FakeBackend, FakeClock


class FakeApi:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []
        self.deleted: list[tuple[int, int]] = []

    async def get_updates(self, offset: int, poll_seconds: int) -> list[dict[str, Any]]:
        return []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))


def update(
    update_id: int, text: str, *, user: int = 42, chat_type: str = "private"
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "text": text,
            "from": {"id": user, "username": "emirhan"},
            "chat": {"id": user, "type": chat_type},
        },
    }


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.clock = FakeClock()
        counter = iter(range(1, 100_000))
        token = lambda n: bytes(next(counter) % 256 for _ in range(n))  # noqa: E731
        self.registry = DeviceRegistry(tmp_path / "d.json", self.clock, token_bytes=token)
        self.pairing = PairingService(
            self.registry, self.clock, token_bytes=lambda n: bytes(range(n))
        )
        self.store = TaskStore(self.clock, token_bytes=token)
        self.backend = FakeBackend()
        self.service = RemoteService(
            clock=self.clock, registry=self.registry, store=self.store, backend=self.backend
        )
        self.api = FakeApi()
        self.bridge = TelegramBridge(
            api=self.api,
            service=self.service,
            registry=self.registry,
            pairing=self.pairing,
            store=self.store,
            clock=self.clock,
            offsets=OffsetStore(tmp_path / "offset.json"),
        )

    async def pair_user(self, scopes: list[str] | None = None) -> str:
        code, _ = self.pairing.begin(scopes, channel=CHANNEL_TELEGRAM)
        await self.bridge.handle_update(update(1, f"/pair {code}"))
        self.pairing.approve(code)
        return code


@pytest.fixture
async def harness(tmp_path: Path) -> Any:
    instance = Harness(tmp_path)
    yield instance
    await instance.service.aclose()


async def test_eslesmemis_kullaniciya_cevap_yok_ve_gorev_acilmaz(harness: Harness) -> None:
    await harness.bridge.handle_update(update(1, "kodu sil"))
    assert harness.api.sent == [] and harness.store.list_tasks() == []


async def test_pair_masaustu_onayi_olmadan_calismaz_sonra_calisir(harness: Harness) -> None:
    code, _ = harness.pairing.begin(None, channel=CHANNEL_TELEGRAM)
    await harness.bridge.handle_update(update(1, f"/pair {code}"))
    assert "masaüstü" in harness.api.sent[-1][1]
    await harness.bridge.handle_update(update(2, "gorev yap"))
    assert harness.store.list_tasks() == []  # henüz onaysız
    harness.pairing.approve(code)
    await harness.bridge.handle_update(update(3, "gorev yap"))
    assert len(harness.store.list_tasks()) == 1


async def test_yanlis_kanal_kodu_ve_hiz_siniri(harness: Harness) -> None:
    signed_code, _ = harness.pairing.begin(None)  # imzalı kanal kodu
    await harness.bridge.handle_update(update(1, f"/pair {signed_code}"))
    assert "geçersiz" in harness.api.sent[-1][1]
    for index in range(2, 8):
        await harness.bridge.handle_update(update(index, "/pair YANLIS12"))
    count = len(harness.api.sent)
    await harness.bridge.handle_update(update(20, "/pair YANLIS12"))
    assert len(harness.api.sent) == count  # kilitlendi: sessiz


async def test_grup_sohbeti_ve_tekrar_eden_guncelleme_yok_sayilir(harness: Harness) -> None:
    await harness.pair_user()
    await harness.bridge.handle_update(update(5, "grup işi", chat_type="group"))
    assert harness.store.list_tasks() == []
    await harness.bridge.handle_update(update(6, "tek iş"))
    await harness.bridge.handle_update(update(6, "tek iş"))  # aynı update_id
    await asyncio.sleep(0.01)
    assert len(harness.store.list_tasks()) == 1 and len(harness.backend.started) == 1


async def test_sir_iceren_mesaj_islenmez_ve_silinmeye_calisilir(harness: Harness) -> None:
    await harness.pair_user()
    await harness.bridge.handle_update(
        update(9, "token: 123456:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789")
    )
    assert harness.store.list_tasks() == []
    assert harness.api.deleted == [(42, 9)]


async def test_offset_kalici_yeniden_baslatmada_tekrar_islenmez(
    harness: Harness, tmp_path: Path
) -> None:
    await harness.pair_user()
    await harness.bridge.handle_update(update(11, "bir"))
    restarted = OffsetStore(tmp_path / "offset.json")
    assert restarted.load() == 12


async def test_onay_bildirimi_dugmesiz_ve_step_up_metni(harness: Harness) -> None:
    harness.backend.ask = {"tur": "onay", "arac": "desktop_click", "baslik": "Tıkla", "hedef": "x"}
    await harness.pair_user(["project.read", "agent.run"])
    await harness.bridge.handle_update(update(7, "iş yap"))
    await asyncio.sleep(0.05)
    await harness.bridge.notify()
    assert any("masaüstü" in text for _, text in harness.api.sent)
    harness.backend.release.set()


async def test_kapsamsiz_kit_komutu_reddedilir(harness: Harness) -> None:
    await harness.pair_user(["project.read", "agent.run", "kits.list"])
    await harness.bridge.handle_update(update(8, "/kit acik"))
    assert "yetkisi" in harness.api.sent[-1][1]
    await harness.bridge.handle_update(update(9, "/kits"))
    assert "acik" in harness.api.sent[-1][1]

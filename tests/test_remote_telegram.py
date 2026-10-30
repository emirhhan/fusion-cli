"""Telegram köprüsü: eşleştirme, DM-only, tekrar önleme, sır reddi, step-up bildirimi."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from fusion_cli.memory.run_store import SqliteRunStore
from fusion_cli.remote.devices import CHANNEL_TELEGRAM, DeviceRegistry
from fusion_cli.remote.pairing import PairingService
from fusion_cli.remote.rpc import RemoteService
from fusion_cli.remote.tasks import TaskStore
from fusion_cli.remote.telegram import OffsetStore, TelegramBridge
from tests.test_remote_service import FakeBackend, FakeClock


class FakeApi:
    def __init__(self) -> None:
        #: (sohbet, metin, düğmeler) — düğmeler P-040 ile geldi; eski testler ilk ikisini okur.
        self.sent: list[tuple[int, str, tuple[tuple[str, str], ...]]] = []
        self.deleted: list[tuple[int, int]] = []
        self.callbacks: list[tuple[str, str]] = []

    async def get_updates(self, offset: int, poll_seconds: int) -> list[dict[str, Any]]:
        return []

    async def send_message(
        self, chat_id: int, text: str, buttons: tuple[tuple[str, str], ...] = ()
    ) -> None:
        self.sent.append((chat_id, text, buttons))

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))

    async def answer_callback(self, callback_id: str, text: str) -> None:
        self.callbacks.append((callback_id, text))


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


def _yerel_sahip():
    """Masaüstündeki yerel sahip: hesapsız kurulumda eski cihazlar bu tenant'tadır."""
    from fusion_cli.accounts.workspaces import PERSONAL_WORKSPACE, bind_context, local_identity

    return bind_context(local_identity(""), PERSONAL_WORKSPACE)


class Harness:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.clock = FakeClock()
        counter = iter(range(1, 100_000))
        token = lambda n: bytes(next(counter) % 256 for _ in range(n))  # noqa: E731
        self.registry = DeviceRegistry(tmp_path / "d.json", self.clock, token_bytes=token)
        self.pairing = PairingService(
            self.registry, self.clock, token_bytes=lambda n: bytes(range(n))
        )
        self.store = TaskStore(
            SqliteRunStore(tmp_path / "runs.sqlite3", clock=self.clock, token_bytes=token)
        )
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
    assert harness.api.sent == [] and harness.store.list_tasks(_yerel_sahip()) == []


async def test_pair_masaustu_onayi_olmadan_calismaz_sonra_calisir(harness: Harness) -> None:
    code, _ = harness.pairing.begin(None, channel=CHANNEL_TELEGRAM)
    await harness.bridge.handle_update(update(1, f"/pair {code}"))
    assert "masaüstü" in harness.api.sent[-1][1]
    await harness.bridge.handle_update(update(2, "gorev yap"))
    assert harness.store.list_tasks(_yerel_sahip()) == []  # henüz onaysız
    harness.pairing.approve(code)
    await harness.bridge.handle_update(update(3, "gorev yap"))
    assert len(harness.store.list_tasks(_yerel_sahip())) == 1


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
    assert harness.store.list_tasks(_yerel_sahip()) == []
    await harness.bridge.handle_update(update(6, "tek iş"))
    await harness.bridge.handle_update(update(6, "tek iş"))  # aynı update_id
    await asyncio.sleep(0.01)
    assert len(harness.store.list_tasks(_yerel_sahip())) == 1 and len(harness.backend.started) == 1


async def test_sir_iceren_mesaj_islenmez_ve_silinmeye_calisilir(harness: Harness) -> None:
    await harness.pair_user()
    await harness.bridge.handle_update(
        update(9, "token: 123456:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789")
    )
    assert harness.store.list_tasks(_yerel_sahip()) == []
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
    assert any("masaüstü" in text for _, text, _buttons in harness.api.sent)
    harness.backend.release.set()


async def test_kapsamsiz_kit_komutu_reddedilir(harness: Harness) -> None:
    await harness.pair_user(["project.read", "agent.run", "kits.list"])
    await harness.bridge.handle_update(update(8, "/kit acik"))
    assert "yetkisi" in harness.api.sent[-1][1]
    await harness.bridge.handle_update(update(9, "/kits"))
    assert "acik" in harness.api.sent[-1][1]


async def test_yeniden_baslatmada_eski_bildirimler_tekrar_gonderilmez(harness: Harness) -> None:
    """Görevler kalıcı; köprü yeniden kurulunca geçmiş onay/bitiş bildirimleri yinelenmez."""
    harness.backend.ask = {"tur": "onay", "arac": "desktop_click", "baslik": "Tıkla", "hedef": "x"}
    await harness.pair_user(["project.read", "agent.run"])
    await harness.bridge.handle_update(update(7, "iş yap"))
    await asyncio.sleep(0.05)
    await harness.bridge.notify()
    harness.clock.value += 60
    yeni = TelegramBridge(
        api=harness.api,
        service=harness.service,
        registry=harness.registry,
        pairing=harness.pairing,
        store=harness.store,
        clock=harness.clock,
        offsets=OffsetStore(harness.tmp / "offset2.json"),
    )
    yeni._chats = dict(harness.bridge._chats)
    gonderilen = len(harness.api.sent)

    await yeni.notify()

    assert len(harness.api.sent) == gonderilen
    harness.backend.release.set()


class _Kopuk(FakeApi):
    """`get_updates` sırayla verilen yanıtları/istisnaları üretir."""

    def __init__(self, steps: list[Any], stop: asyncio.Event) -> None:
        super().__init__()
        self.steps = steps
        self.stop = stop

    async def get_updates(self, offset: int, poll_seconds: int) -> list[dict[str, Any]]:
        if not self.steps:
            self.stop.set()
            return []
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


async def test_run_telegram_disi_istisnada_kopmaz_hatayi_bildirir(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fusion_cli.remote import telegram as telegram_module

    monkeypatch.setattr(telegram_module, "RETRY_SECONDS", 0)
    stop = asyncio.Event()
    harness.bridge._api = _Kopuk([KeyError("id"), []], stop)  # type: ignore[assignment]
    errors: list[str] = []

    async def on_error(message: str) -> None:
        errors.append(message)

    await asyncio.wait_for(harness.bridge.run(stop, on_error), 5)
    assert errors and "KeyError" in errors[0]


async def test_ofset_isleme_bittikten_sonra_kaydedilir_zehirli_guncelleme_atlanir(
    harness: Harness, tmp_path: Path
) -> None:
    await harness.pair_user()
    seen: list[int] = []

    async def bozuk(_device: Any, _text: str, _update_id: int) -> str:
        seen.append(OffsetStore(tmp_path / "offset.json").load())
        raise KeyError("beklenmeyen")

    harness.bridge._dispatch = bozuk  # type: ignore[method-assign]
    errors: list[str] = []

    async def on_error(message: str) -> None:
        errors.append(message)

    class Tek(FakeApi):
        async def get_updates(self, offset: int, poll_seconds: int) -> list[dict[str, Any]]:
            return [update(30, "merhaba")] if offset <= 30 else []

    harness.bridge._api = Tek()  # type: ignore[assignment]
    await harness.bridge.poll_once(0, on_error)
    assert seen == [2]  # işleme sırasında kalıcı ofset henüz 30'u içermiyor
    assert OffsetStore(tmp_path / "offset.json").load() == 31  # zehirli güncelleme atlandı
    assert errors and "KeyError" in errors[0]


async def test_bildirim_gonderimi_basarisizsa_olay_kaybolmaz(harness: Harness) -> None:
    from fusion_cli.remote.telegram import TelegramError

    harness.backend.ask = {"tur": "onay", "arac": "desktop_click", "baslik": "Tıkla", "hedef": "x"}
    await harness.pair_user(["project.read", "agent.run"])
    await harness.bridge.handle_update(update(7, "iş yap"))
    await asyncio.sleep(0.05)
    gonderilen = len(harness.api.sent)
    gercek = harness.api.send_message
    kalan = {"hata": 1}

    async def kirilgan(chat_id: int, text: str, buttons: tuple[tuple[str, str], ...] = ()) -> None:
        if kalan["hata"]:
            kalan["hata"] -= 1
            raise TelegramError("ağ")
        await gercek(chat_id, text, buttons)

    harness.api.send_message = kirilgan  # type: ignore[method-assign]
    with pytest.raises(TelegramError):
        await harness.bridge.notify()
    await harness.bridge.notify()  # ikinci deneme aynı olayı yeniden gönderir
    assert len(harness.api.sent) > gonderilen
    assert any("masaüstü" in text for _, text, _buttons in harness.api.sent[gonderilen:])
    harness.backend.release.set()


async def test_parola_kelimesi_gecen_meşru_mesaj_islenir_gercek_sir_reddedilir(
    harness: Harness,
) -> None:
    await harness.pair_user()
    await harness.bridge.handle_update(update(40, "token ekle: foo"))
    assert len(harness.store.list_tasks(_yerel_sahip())) == 1
    await harness.bridge.handle_update(update(41, "password: hunter2"))
    assert harness.api.deleted == [(42, 41)]  # düz anahtar=değer kalıbı sır sayılır
    assert len(harness.store.list_tasks(_yerel_sahip())) == 1


def test_yardim_metni_desteklenmeyen_duraklatmayi_sunmaz() -> None:
    """R1-18. Ölçüldü (30 Ekim): yardım /pause /resume sunuyor, ikisi 'desteklenmiyor' dönüyordu."""
    from fusion_cli.remote.telegram import HELP_TEXT

    assert "/pause" not in HELP_TEXT and "/resume" not in HELP_TEXT

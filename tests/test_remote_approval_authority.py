"""Uzaktan onay yetkisi (P-040): cihaz başına süreli yetki, Telegram onay düğmeleri.

Ölçüldü (31 Ekim): eski kodda telefon kapsam + ikinci teyitle her onayı verebiliyor,
masaüstünün "bu cihaz onay verebilir (N saat)" diyebileceği bir yetki yoktu; Telegram'dan
onay HİÇ verilemiyordu (düğme ve komut yok), bildirim yalnız "masaüstünde onayla" diyordu.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from fusion_cli.memory.run_store import SqliteRunStore
from fusion_cli.remote.constants import APPROVAL_TRUST_MAX_HOURS
from fusion_cli.remote.controller import RemoteController
from fusion_cli.remote.devices import CHANNEL_SIGNED, DeviceRegistry
from fusion_cli.remote.pairing import PairingService
from fusion_cli.remote.rpc import RemoteService
from fusion_cli.remote.tasks import TaskStore
from fusion_cli.remote.telegram import BUTTON_ALLOW, BUTTON_DENY, CALLBACK_PREFIX
from tests.test_remote_controller import MemorySecrets
from tests.test_remote_service import FakeBackend, FakeClock
from tests.test_remote_telegram import Harness, update

_KABUK_SORUSU = {
    "tur": "onay",
    "arac": "run_shell",
    "baslik": "Komut çalıştır",
    "hedef": "pytest",
    "secenekler": [{"deger": "once"}, {"deger": "deny"}],
}


def _service(
    tmp_path: Path, *, require_trust: bool
) -> tuple[RemoteService, DeviceRegistry, FakeBackend, FakeClock]:
    clock = FakeClock()
    registry = DeviceRegistry(tmp_path / "devices.json", clock)
    backend = FakeBackend()
    service = RemoteService(
        clock=clock,
        registry=registry,
        backend=backend,
        store=TaskStore(SqliteRunStore(tmp_path / "runs.sqlite3", clock=clock)),
        require_approval_trust=lambda: require_trust,
    )
    return service, registry, backend, clock


async def test_yetki_zorunluyken_yetkisiz_telefon_yalniz_reddedebilir(tmp_path: Path) -> None:
    service, registry, backend, _clock = _service(tmp_path, require_trust=True)
    phone = registry.add("Tel", CHANNEL_SIGNED, frozenset({"agent.run", "project.write"}))
    service._questions["q"] = ("run", dict(_KABUK_SORUSU))

    onay = await service.call(phone, "approvals.respond", {"questionId": "q", "choice": "once"})
    teyit = await service.call(phone, "approvals.challenge", {"questionId": "q", "choice": "once"})
    durum = await service.call(phone, "service.status", {})
    red = await service.call(phone, "approvals.respond", {"questionId": "q", "choice": "deny"})

    assert (onay.error, teyit.error) == ("onay_yetkisi_yok", "onay_yetkisi_yok")
    assert durum.data["approvalAuthority"] == {
        "required": True,
        "secondsLeft": 0,
        "canApprove": False,
    }
    assert red.ok and backend.answers == [("q", {"secim": "deny"})]


async def test_sureli_yetki_verilen_telefon_onaylar_sure_dolunca_yine_reddedilir(
    tmp_path: Path,
) -> None:
    service, registry, backend, clock = _service(tmp_path, require_trust=True)
    phone = registry.add("Tel", CHANNEL_SIGNED, frozenset({"agent.run", "project.write"}))
    assert registry.set_approval_trust(phone.device_id, 18)
    service._questions["q"] = ("run", dict(_KABUK_SORUSU))

    kabul = await service.call(phone, "approvals.respond", {"questionId": "q", "choice": "once"})
    assert kabul.ok and backend.answers[-1] == ("q", {"secim": "once"})
    durum = await service.call(phone, "service.status", {})
    assert durum.data["approvalAuthority"]["canApprove"] is True
    assert durum.data["approvalAuthority"]["secondsLeft"] == 18 * 3600

    clock.value += 18 * 3600 + 1
    service._questions["q2"] = ("run", dict(_KABUK_SORUSU))
    gec = await service.call(phone, "approvals.respond", {"questionId": "q2", "choice": "once"})
    assert gec.error == "onay_yetkisi_yok"


async def test_yetki_zorunlu_degilken_eski_davranis_korunur(tmp_path: Path) -> None:
    """Varsayılan kapalı: kapsamlı telefon yetkisiz de onaylar (geri uyumluluk)."""
    service, registry, backend, _clock = _service(tmp_path, require_trust=False)
    phone = registry.add("Tel", CHANNEL_SIGNED, frozenset({"agent.run", "project.write"}))
    service._questions["q"] = ("run", dict(_KABUK_SORUSU))
    kabul = await service.call(phone, "approvals.respond", {"questionId": "q", "choice": "once"})
    assert kabul.ok and backend.answers == [("q", {"secim": "once"})]


def test_yetki_kalici_tavanli_ve_iptalde_kalkar(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = DeviceRegistry(tmp_path / "d.json", clock)
    phone = registry.add("Tel", CHANNEL_SIGNED, frozenset({"agent.run"}))
    assert not registry.set_approval_trust(phone.device_id, APPROVAL_TRUST_MAX_HOURS + 1)
    assert not registry.set_approval_trust(phone.device_id, -1)
    assert registry.set_approval_trust(phone.device_id, 2)
    assert registry.approval_trust_remaining(phone.device_id) == 2 * 3600
    assert registry.get(phone.device_id).public_view()["approvalTrustedUntil"] > 0  # type: ignore[union-attr]

    yeniden = DeviceRegistry(tmp_path / "d.json", clock)
    assert yeniden.has_approval_trust(phone.device_id)
    assert yeniden.set_approval_trust(phone.device_id, 0)
    assert not yeniden.has_approval_trust(phone.device_id)

    assert registry.set_approval_trust(phone.device_id, 2)
    registry.revoke(phone.device_id)
    assert not registry.has_approval_trust(phone.device_id)
    assert registry.get(phone.device_id).approval_trusted_until == 0.0  # type: ignore[union-attr]


def test_eslestirmede_verilen_onay_saati_cihaza_islenir(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = DeviceRegistry(tmp_path / "d.json", clock)
    pairing = PairingService(registry, clock, require_approval=lambda: True)
    code, _ = pairing.begin(["project.read", "agent.run"], approval_hours=18)
    pairing.submit(code, "Telefon")
    device = pairing.approve(code)
    assert registry.approval_trust_remaining(device.device_id) == 18 * 3600

    code2, _ = pairing.begin(["project.read", "agent.run"])
    pairing.submit(code2, "Telefon 2")
    assert registry.approval_trust_remaining(pairing.approve(code2).device_id) == 0


# --------------------------------------------------------------------------- #
# Masaüstü yönetim yüzü
# --------------------------------------------------------------------------- #


@pytest.fixture
async def harness(tmp_path: Path) -> Any:
    instance = Harness(tmp_path)
    yield instance
    await instance.service.aclose()


@pytest.fixture
async def controller(tmp_path: Path) -> Any:
    instance = RemoteController(
        home=tmp_path,
        root=tmp_path,
        secrets=MemorySecrets(),
        session_factory=lambda writer: object(),
        clock=FakeClock(),
    )
    yield instance
    await instance.aclose()


async def test_masaustu_onay_yetkisi_ayari_ve_cihaz_yetkisi(
    controller: Any, tmp_path: Path
) -> None:
    durum = await controller.dispatch("uzak.durum", {})
    assert durum["onayYetkisiIste"] is False and durum["onayYetkisiVarsayilanSaat"] == 18

    ayar = await controller.dispatch("uzak.ayar", {"onayYetkisiIste": True})
    assert ayar == {"ok": True, "onayIste": False, "onayYetkisiIste": True}
    assert (await controller.dispatch("uzak.ayar", {"onayYetkisiIste": "evet"}))["ok"] is False
    # Eski tek alanlı çağrı aynen çalışır; diğer bayrak korunur.
    assert (await controller.dispatch("uzak.ayar", {"onayIste": True}))["onayYetkisiIste"] is True

    basla = await controller.dispatch(
        "uzak.eslestir_baslat", {"kapsamlar": ["project.read", "agent.run"], "onaySaat": 18}
    )
    assert basla["onaySaat"] == 18
    assert (await controller.dispatch("uzak.eslestir_baslat", {"onaySaat": 999}))["ok"] is False
    controller._pairing.submit(basla["kod"], "Telefon")
    onay = await controller.dispatch("uzak.eslestir_onayla", {"kod": basla["kod"]})
    device_id = onay["cihaz"]["deviceId"]
    assert onay["cihaz"]["approvalTrustedUntil"] > 0

    kaldir = await controller.dispatch("uzak.onay_yetkisi", {"cihazId": device_id, "saat": 0})
    assert kaldir["ok"] and kaldir["cihaz"]["approvalTrustedUntil"] == 0
    ver = await controller.dispatch("uzak.onay_yetkisi", {"cihazId": device_id})
    assert ver["ok"] and ver["cihaz"]["approvalTrustedUntil"] > 0
    assert (await controller.dispatch("uzak.onay_yetkisi", {"cihazId": "yok"}))["ok"] is False

    # Ayar kalıcıdır: yeniden kurulan yönetici aynı değeri okur.
    yeniden = RemoteController(
        home=tmp_path,
        root=tmp_path,
        secrets=MemorySecrets(),
        session_factory=lambda writer: object(),
        clock=FakeClock(),
    )
    try:
        assert (await yeniden.dispatch("uzak.durum", {}))["onayYetkisiIste"] is True
    finally:
        await yeniden.aclose()


# --------------------------------------------------------------------------- #
# Telegram düğmeleri
# --------------------------------------------------------------------------- #


def _callback(
    callback_id: str, data: str, *, user: int = 42, update_id: int = 900
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": callback_id,
            "from": {"id": user},
            "data": data,
            "message": {"message_id": 5, "chat": {"id": user, "type": "private"}},
        },
    }


def _buttons(harness: Harness) -> list[tuple[str, str]]:
    return [button for _chat, _text, buttons in harness.api.sent for button in buttons]


async def test_telegram_kapsamli_cihaza_izin_ver_dugmesi_gelir_ve_tiklaninca_onaylar(
    harness: Harness,
) -> None:
    harness.backend.ask = {
        "tur": "onay",
        "arac": "run_shell",
        "baslik": "Komut çalıştır",
        "hedef": "pytest",
    }
    await harness.pair_user(["project.read", "agent.run", "project.write"])
    await harness.bridge.handle_update(update(7, "testleri koş"))
    await asyncio.sleep(0.05)
    await harness.bridge.notify()

    labels = [label for label, _data in _buttons(harness)]
    assert labels == [BUTTON_ALLOW, BUTTON_DENY]
    assert any("Komut çalıştır" in text for _chat, text, _b in harness.api.sent)
    allow_data = next(data for label, data in _buttons(harness) if label == BUTTON_ALLOW)
    assert allow_data.startswith(CALLBACK_PREFIX) and len(allow_data.encode()) <= 64

    await harness.bridge.handle_update(_callback("cb1", allow_data))
    assert harness.backend.answers and harness.backend.answers[-1][1]["secim"] == "once"
    assert harness.api.callbacks[-1][1].startswith("Onay iletildi")
    # Aynı düğme ikinci kez geçersizdir.
    await harness.bridge.handle_update(_callback("cb2", allow_data, update_id=901))
    assert len(harness.backend.answers) == 1
    assert harness.api.callbacks[-1][1] == "Bu onay artık geçerli değil."
    harness.backend.release.set()


async def test_telegram_yabanci_kullanici_dugmeyi_kullanamaz(harness: Harness) -> None:
    harness.backend.ask = {"tur": "onay", "arac": "run_shell", "baslik": "Komut", "hedef": "x"}
    await harness.pair_user(["project.read", "agent.run", "project.write"])
    await harness.bridge.handle_update(update(7, "iş"))
    await asyncio.sleep(0.05)
    await harness.bridge.notify()
    allow_data = next(data for label, data in _buttons(harness) if label == BUTTON_ALLOW)

    await harness.bridge.handle_update(_callback("cb9", allow_data, user=777))
    assert harness.backend.answers == []
    assert harness.api.callbacks == [("cb9", "Bu onay artık geçerli değil.")]
    harness.backend.release.set()


async def test_telegram_step_up_ve_kapsamsiz_onayda_yalniz_reddet(harness: Harness) -> None:
    harness.backend.ask = {"tur": "onay", "arac": "desktop_click", "baslik": "Tıkla", "hedef": "x"}
    await harness.pair_user(["project.read", "agent.run", "project.write", "desktop.control"])
    await harness.bridge.handle_update(update(7, "tıkla"))
    await asyncio.sleep(0.05)
    await harness.bridge.notify()
    assert [label for label, _d in _buttons(harness)] == [BUTTON_DENY]
    assert any("masaüstü" in text for _c, text, _b in harness.api.sent)
    deny_data = _buttons(harness)[0][1]
    await harness.bridge.handle_update(_callback("cb3", deny_data))
    assert harness.backend.answers[-1][1]["secim"] == "deny"
    harness.backend.release.set()


async def test_telegram_kapsami_yetmeyen_cihaza_izin_ver_sunulmaz(harness: Harness) -> None:
    harness.backend.ask = {"tur": "onay", "arac": "run_shell", "baslik": "Komut", "hedef": "x"}
    await harness.pair_user(["project.read", "agent.run"])
    await harness.bridge.handle_update(update(7, "iş"))
    await asyncio.sleep(0.05)
    await harness.bridge.notify()
    assert [label for label, _d in _buttons(harness)] == [BUTTON_DENY]
    assert any("project.write" in text for _c, text, _b in harness.api.sent)
    harness.backend.release.set()

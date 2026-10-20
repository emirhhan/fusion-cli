"""Kodla eşleştirme: doğru kod PWA kanalında kendiliğinden onaylanır; ayar ve bildirim."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from fusion_cli.remote.asgi import RemoteApp
from fusion_cli.remote.controller import RemoteController
from fusion_cli.remote.devices import CHANNEL_TELEGRAM, Device, DeviceRegistry
from fusion_cli.remote.pairing import PairingError, PairingService
from fusion_cli.remote.rate_limit import FailureLimiter
from fusion_cli.remote.signing import SignatureVerifier
from tests.test_remote_controller import MemorySecrets
from tests.test_remote_service import FakeClock, Rig


def _service(tmp_path: Path, *, require: bool) -> tuple[PairingService, list[Device]]:
    clock = FakeClock()
    seen: list[Device] = []
    service = PairingService(
        DeviceRegistry(tmp_path / "d.json", clock),
        clock,
        require_approval=lambda: require,
        on_paired=seen.append,
    )
    return service, seen


def test_ayar_kapaliyken_dogru_kod_kendiliginden_onaylanir(tmp_path: Path) -> None:
    service, seen = _service(tmp_path, require=False)
    code, _ = service.begin(None)
    service.submit(code, "Telefonum", channel="signed")
    assert service.is_approved(code) and [d.name for d in seen] == ["Telefonum"]
    device = service.claim(code)
    assert device is not None and device.name == "Telefonum"
    with pytest.raises(PairingError):
        service.claim(code)


def test_onay_iste_acikken_masaustu_onayi_beklenir(tmp_path: Path) -> None:
    service, seen = _service(tmp_path, require=True)
    code, _ = service.begin(None)
    service.submit(code, "Telefonum", channel="signed")
    assert not service.is_approved(code) and service.claim(code) is None and not seen
    service.approve(code)
    assert [d.name for d in seen] == ["Telefonum"]


def test_yanlis_kod_onaylanmaz_ve_telegram_kanali_eskisi_gibi(tmp_path: Path) -> None:
    service, seen = _service(tmp_path, require=False)
    with pytest.raises(PairingError):
        service.submit("YANLIS12", "Telefonum", channel="signed")
    code, _ = service.begin(None, channel=CHANNEL_TELEGRAM)
    service.submit(code, "Bot", external_id="42")
    assert not service.is_approved(code) and not seen  # Telegram her zaman elle onay


async def _http(rig: Rig, require: bool) -> httpx.AsyncClient:
    rig.pairing = PairingService(rig.registry, rig.clock, require_approval=lambda: require)
    rig.app = RemoteApp(
        service=rig.service,
        registry=rig.registry,
        pairing=rig.pairing,
        verifier=SignatureVerifier(rig.clock),
        limiter=FailureLimiter(rig.clock),
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=rig.app), base_url="http://x")


@pytest.fixture
async def rig(tmp_path: Path) -> Any:
    instance = Rig(tmp_path)
    yield instance
    await instance.service.aclose()


async def test_http_gonderim_onaylandi_dondurur_ve_cihaz_hemen_alinir(rig: Rig) -> None:
    client = await _http(rig, require=False)
    code, _ = rig.pairing.begin(None)
    submit = await client.post("/v1/pair/submit", json={"code": code, "deviceName": "iPhone"})
    assert submit.json()["state"] == "onaylandi"
    claim = (await client.post("/v1/pair/claim", json={"code": code})).json()
    assert claim["state"] == "onaylandi" and claim["deviceId"] and claim["secret"]


async def test_http_onay_iste_acikken_bekliyor_dondurur(rig: Rig) -> None:
    client = await _http(rig, require=True)
    code, _ = rig.pairing.begin(None)
    submit = await client.post("/v1/pair/submit", json={"code": code, "deviceName": "iPhone"})
    assert submit.json()["state"] == "onay_bekliyor"
    assert (await client.post("/v1/pair/claim", json={"code": code})).json() == {
        "state": "onay_bekliyor"
    }


def _controller(tmp_path: Path) -> RemoteController:
    return RemoteController(
        home=tmp_path,
        root=tmp_path,
        secrets=MemorySecrets(),
        session_factory=lambda writer: object(),
        clock=FakeClock(),
    )


async def test_ayar_varsayilan_kapali_kalici_ve_durumda_gorunur(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    assert (await controller.dispatch("uzak.durum", {}))["onayIste"] is False
    assert (await controller.dispatch("uzak.ayar", {"onayIste": "evet"}))["ok"] is False
    assert (await controller.dispatch("uzak.ayar", {"onayIste": True}))["onayIste"] is True
    await controller.aclose()
    again = _controller(tmp_path)
    assert (await again.dispatch("uzak.durum", {}))["onayIste"] is True
    await again.aclose()


async def test_eslesen_cihaz_durumda_son_eslesen_olarak_gorunur(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    assert (await controller.dispatch("uzak.durum", {}))["sonEslesen"] is None
    code = (await controller.dispatch("uzak.eslestir_baslat", {"kanal": "pwa"}))["kod"]
    controller._pairing.submit(code, "Telefonum", channel="signed")  # ayar kapalı → otomatik
    last = (await controller.dispatch("uzak.durum", {}))["sonEslesen"]
    assert last["ad"] == "Telefonum"
    devices = (await controller.dispatch("uzak.cihazlar", {}))["cihazlar"]
    assert [d["name"] for d in devices] == ["Telefonum"]
    await controller.aclose()

"""Telefona canlı ekran: onay, süre, hız sınırı, yetki ve masaüstü kesme."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from fusion_cli.remote.controller import RemoteController
from fusion_cli.remote.rpc import RemoteService
from fusion_cli.remote.screen import (
    MacScreenCapture,
    ScreenShareGate,
    ScreenUnavailableError,
)
from fusion_cli.remote.tasks import TaskStore
from tests.test_remote_controller import MemorySecrets
from tests.test_remote_service import FakeBackend, FakeClock


class FakeCapture:
    def __init__(self) -> None:
        self.calls = 0
        self.fail: str | None = None

    async def frame(self) -> bytes:
        self.calls += 1
        if self.fail:
            raise ScreenUnavailableError(self.fail)
        return b"\xff\xd8jpeg"


@pytest.fixture
def parts(tmp_path: Path) -> Any:
    from fusion_cli.remote.devices import DeviceRegistry

    clock = FakeClock()
    registry = DeviceRegistry(tmp_path / "d.json", clock)
    capture = FakeCapture()
    service = RemoteService(
        clock=clock,
        registry=registry,
        store=TaskStore(clock),
        backend=FakeBackend(),
        screen_capture=capture,
    )
    observer = registry.add("Tel", "signed", frozenset({"project.read", "desktop.observe"}))
    plain = registry.add("Tel2", "signed", frozenset({"project.read"}))
    return clock, service, observer, plain, capture


async def test_onay_olmadan_kare_verilmez_yakalama_cagrilmaz(parts: Any) -> None:
    _clock, service, observer, _plain, capture = parts
    result = await service.call(observer, "screen.frame", {})
    assert result.error == "ekran_onay_yok" and capture.calls == 0


async def test_istek_onay_kare_ve_durdurma_akisi(parts: Any) -> None:
    clock, service, observer, _plain, capture = parts
    assert (await service.call(observer, "screen.request", {})).data["state"] == "pending"
    assert service.screen_gate.pending() == [observer.device_id]
    assert (await service.call(observer, "screen.frame", {})).error == "ekran_onay_yok"
    assert service.screen_gate.approve(observer.device_id) is True
    clock.value += 1
    frame = await service.call(observer, "screen.frame", {})
    assert frame.ok and base64.b64decode(frame.data["jpegBase64"]).startswith(b"\xff\xd8")
    assert frame.data["seq"] == 1 and capture.calls == 1
    status = await service.call(observer, "screen.status", {})
    assert status.data["state"] == "active" and 0 < status.data["secondsLeft"] <= 300
    assert (await service.call(observer, "screen.stop", {})).data["stopped"] is True
    assert (await service.call(observer, "screen.frame", {})).error == "ekran_onay_yok"


async def test_kare_hiz_siniri_ve_suresi_dolan_oturum(parts: Any) -> None:
    clock, service, observer, _plain, capture = parts
    await service.call(observer, "screen.request", {})
    service.screen_gate.approve(observer.device_id)
    clock.value += 1
    assert (await service.call(observer, "screen.frame", {})).ok
    assert (await service.call(observer, "screen.frame", {})).error == "cok_sik"
    clock.value += 0.6
    assert (await service.call(observer, "screen.frame", {})).data["seq"] == 2
    clock.value += 301
    assert (await service.call(observer, "screen.frame", {})).error == "ekran_onay_yok"
    assert capture.calls == 2


async def test_kapsam_olmayan_cihaz_ekran_isteyemez(parts: Any) -> None:
    _clock, service, _observer, plain, _capture = parts
    for method in ("screen.request", "screen.frame", "screen.status"):
        assert (await service.call(plain, method, {})).error == "yetki_yok"


async def test_yakalama_hatasi_dogru_kodla_doner(parts: Any) -> None:
    clock, service, observer, _plain, capture = parts
    await service.call(observer, "screen.request", {})
    service.screen_gate.approve(observer.device_id)
    clock.value += 1
    capture.fail = "Ekran Kaydı izni gerekebilir."
    result = await service.call(observer, "screen.frame", {})
    assert result.error == "ekran_kullanilamaz" and "izni" in result.message


async def test_baska_cihazin_onayi_digerine_gecmez() -> None:
    clock = FakeClock()
    gate = ScreenShareGate(clock)
    gate.request("a")
    gate.request("b")
    assert gate.approve("a") is True
    assert gate.status("b")[0] == "pending" and gate.next_sequence("b") == "onay_yok"
    assert gate.approve("a") is False  # zaten etkin


async def test_masaustu_bekleyeni_listeler_onaylar_ve_keser(tmp_path: Path) -> None:
    controller = RemoteController(
        home=tmp_path,
        root=tmp_path,
        secrets=MemorySecrets(),
        session_factory=lambda writer: object(),
        clock=FakeClock(),
    )
    device = controller._registry.add("Telefonum", "signed", frozenset({"desktop.observe"}))
    await controller._service.call(device, "screen.request", {})
    pending = await controller.dispatch("uzak.ekran_bekleyen", {})
    assert pending["bekleyen"] == [{"cihazId": device.device_id, "ad": "Telefonum"}]
    assert (await controller.dispatch("uzak.ekran_onayla", {"cihazId": device.device_id}))["ok"]
    assert (await controller.dispatch("uzak.ekran_bekleyen", {}))["etkin"][0]["ad"] == "Telefonum"
    assert (await controller.dispatch("uzak.ekran_kes", {"cihazId": device.device_id}))["ok"]
    assert (await controller.dispatch("uzak.ekran_bekleyen", {}))["etkin"] == []
    await controller.aclose()


async def test_gercek_yakalama_jpeg_uretir_ya_da_dogru_hata_verir() -> None:
    import platform

    capture = MacScreenCapture()
    if platform.system() != "Darwin":
        with pytest.raises(ScreenUnavailableError):
            await capture.frame()
        return
    try:
        frame = await capture.frame()
    except ScreenUnavailableError:
        pytest.skip("Ekran Kaydı izni yok")
    assert frame[:2] == b"\xff\xd8" and 2_000 < len(frame) < 2_000_000

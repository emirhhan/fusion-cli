"""Masaüstüsüz uzaktan kontrol sunucusu (P-039): başlatma, kod, eşleştirme, fark satırları.

Ölçüldü (31 Ekim): eski kodda `remote.host` ve `fusion remote-control` yoktu; uzak yüz yalnız
masaüstü `uzak.*` istekleriyle kalkıyordu.
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

from fusion_cli.core.errors import FusionError
from fusion_cli.remote.controller import RemoteController
from fusion_cli.remote.host import (
    TEXT_TELEGRAM_MISSING,
    PendingApproval,
    RemoteControlError,
    RemoteControlHost,
    RemoteControlSnapshot,
    TaskLine,
)
from tests.test_remote_controller import MemorySecrets
from tests.test_remote_service import FakeClock


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def controller(tmp_path: Path) -> RemoteController:
    return RemoteController(
        home=tmp_path,
        root=tmp_path,
        secrets=MemorySecrets(),
        session_factory=lambda writer: object(),
        clock=FakeClock(),
    )


async def test_baslat_kod_verir_telefon_eslesir_ve_fark_satiri_cikar(
    controller: RemoteController,
) -> None:
    host = RemoteControlHost(controller)
    port = _free_port()
    start = await host.start(port=port, tunnel=True)
    try:
        assert start.address == f"http://127.0.0.1:{port}" and len(start.code) == 8
        assert start.scopes == ("agent.cancel", "agent.run", "project.read")
        assert not start.needs_desktop_approval and start.warnings == ()
        before = await host.snapshot()
        assert before.listening and before.device_count == 0 and before.awaiting_device == ""

        controller._pairing.submit(start.code, "Telefonum")  # imzalı kanal: doğru kod yeter
        after = await host.snapshot()
        assert after.device_count == 1 and after.last_paired == "Telefonum"
        assert host.changes(before, after) == ["Telefonum bağlandı."]
        assert host.changes(after, after) == []
    finally:
        await host.stop()
    assert not host.started
    with pytest.raises(RemoteControlError, match="çalışmıyor"):
        await host.new_code()  # sunucu durdu; kod üretmek anlamsız, Türkçe hata


async def test_yuksek_yetkili_kapsamda_cihaz_terminal_onayi_bekler(
    controller: RemoteController,
) -> None:
    host = RemoteControlHost(controller, extra_scopes=("project.write",), approval_hours=18)
    start = await host.start(port=_free_port(), tunnel=True)
    try:
        assert start.needs_desktop_approval and "project.write" in start.warnings[0]
        controller._pairing.submit(start.code, "Tablet")
        waiting = await host.snapshot()
        assert waiting.awaiting_device == "Tablet" and waiting.device_count == 0
        assert host.changes(RemoteControlSnapshot(True, "", 0, "", 0.0), waiting) == [
            "Tablet kodu girdi; onay bekliyor (`onayla`)."
        ]
        assert await host.approve_pending()
        paired = await host.snapshot()
        assert paired.device_count == 1 and paired.awaiting_device == ""
        device = controller._registry.list_devices()[0]
        assert "project.write" in device.scopes and device.approval_trusted_until > 0
        assert not await host.approve_pending()  # ikinci kez: onaylanacak cihaz yok
    finally:
        await host.stop()


async def test_reddedilen_cihaz_kaydolmaz_ve_kod_duser(controller: RemoteController) -> None:
    host = RemoteControlHost(controller, extra_scopes=("project.write",))
    start = await host.start(port=_free_port(), tunnel=True)
    try:
        controller._pairing.submit(start.code, "Yabancı")
        assert await host.reject_pending()
        assert host.code == "" and controller._registry.list_devices() == []
        code, expires = await host.new_code()
        assert code != start.code and host.code_expired(expires + 1)
        assert not host.code_expired(expires - 1)
    finally:
        await host.stop()


async def test_telegram_belirteci_yoksa_uyari_verir_sunucu_yine_kalkar(
    controller: RemoteController,
) -> None:
    host = RemoteControlHost(controller)
    start = await host.start(port=_free_port(), tunnel=True, telegram=True)
    try:
        assert start.telegram is False and start.warnings == (TEXT_TELEGRAM_MISSING,)
        assert (await host.snapshot()).listening
    finally:
        await host.stop()


async def test_dolu_port_ve_bilinmeyen_kapsam_fusion_hatasi(controller: RemoteController) -> None:
    with pytest.raises(FusionError):
        RemoteControlHost(controller, extra_scopes=("root.all",))
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen(1)
        host = RemoteControlHost(controller)
        with pytest.raises(RemoteControlError, match=str(busy.getsockname()[1])):
            await host.start(port=busy.getsockname()[1], tunnel=True)
    assert not host.started
    await host.stop()  # başlamamış sunucuyu durdurmak zararsız
    await controller.aclose()


def test_fark_satirlari_onay_soru_ve_gorev_durumunu_anlatir() -> None:
    empty = RemoteControlSnapshot(True, "http://127.0.0.1:1", 1, "Tel", 5.0)
    busy = RemoteControlSnapshot(
        True,
        "http://127.0.0.1:1",
        1,
        "Tel",
        5.0,
        pending=(
            PendingApproval("q1", "Komut çalıştır", "pytest", True),
            PendingApproval("q2", "Hangi dal?", "", False),
        ),
        tasks=(TaskLine("r1", "running", "testleri koş"),),
    )
    lines: list[str] = RemoteControlHost.changes(empty, busy)
    assert lines == [
        "Onay bekliyor: Komut çalıştır (pytest) — telefondan ya da Telegram'dan cevapla.",
        "Soru bekliyor: Hangi dal? — telefondan cevapla.",
        "Görev r1: running — testleri koş",
    ]
    done = RemoteControlSnapshot(
        True, "http://127.0.0.1:1", 1, "Tel", 5.0, tasks=(TaskLine("r1", "done", "testleri koş"),)
    )
    assert RemoteControlHost.changes(busy, done) == ["Görev r1: done — testleri koş"]


def _unused(_value: Any) -> None:  # tip denetimi için
    return None

"""Masaüstüsüz uzaktan kontrol sunucusu (P-039): başlatma, kod, eşleştirme, fark satırları.

Ölçüldü (31 Ekim): eski kodda `remote.host` ve `fusion remote-control` yoktu; uzak yüz yalnız
masaüstü `uzak.*` istekleriyle kalkıyordu.
"""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from typing import Any

import pytest

from fusion_cli.core.errors import FusionError
from fusion_cli.remote import controller as controller_module
from fusion_cli.remote.controller import TELEGRAM_TOKEN_NAME, RemoteController
from fusion_cli.remote.devices import CHANNEL_TELEGRAM
from fusion_cli.remote.host import (
    CHANNEL_REQUEST_PWA,
    TEXT_TELEGRAM_MISSING,
    TEXT_TRUST_SETTING_OFF,
    PendingApproval,
    RemoteControlError,
    RemoteControlHost,
    RemoteControlSnapshot,
    TaskLine,
)
from fusion_cli.remote.telegram import OffsetStore, TelegramBridge
from tests.test_remote_controller import MemorySecrets
from tests.test_remote_service import FakeClock
from tests.test_remote_telegram import FakeApi, update


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
        # Yetki şartı (requireApprovalTrust) kapalı: --onay-saat'in neye yaradığı söylenir.
        assert start.warnings[1] == TEXT_TRUST_SETTING_OFF
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


class _NoNetworkTelegramApi:
    """`uzak.telegram_baglan` gerçek `HttpTelegramApi` kurar; testte ağa çıkmayan sahtesi."""

    def __init__(self, _token: str) -> None:
        self.closed = False

    async def get_updates(self, offset: int, poll_seconds: int) -> list[dict[str, Any]]:
        await asyncio.sleep(poll_seconds)
        return []

    async def send_message(self, chat_id: int, text: str, buttons: Any = ()) -> None:
        return None

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        return None

    async def answer_callback(self, callback_id: str, text: str) -> None:
        return None

    async def aclose(self) -> None:
        self.closed = True


async def test_telegram_acikken_ayri_kod_uretilir_ve_pair_komutu_eslesir(
    controller: RemoteController, monkeypatch: Any, tmp_path: Path
) -> None:
    """Ölçüldü (31 Ekim): `--telegram` ile tek kod (PWA kanalı) üretiliyordu; bot `/pair`
    yalnız Telegram kanalı kodunu kabul ettiği için Telegram kullanıcısı hiç eşleşemiyordu."""
    monkeypatch.setattr(controller_module, "HttpTelegramApi", _NoNetworkTelegramApi)
    controller._secrets.set(TELEGRAM_TOKEN_NAME, "123:abc")
    host = RemoteControlHost(controller)
    start = await host.start(port=_free_port(), tunnel=True, telegram=True)
    try:
        assert start.telegram and start.warnings == ()
        assert len(start.telegram_code) == 8 and start.telegram_code != start.code
        assert host.telegram_code == start.telegram_code
        # Gerçek köprü yolu: aynı eşleştirme servisine bağlı bir TelegramBridge `/pair KOD` alır.
        api = FakeApi()
        bridge = TelegramBridge(
            api=api,
            service=controller._service,
            registry=controller._registry,
            pairing=controller._pairing,
            store=controller._store,
            clock=controller._clock,
            offsets=OffsetStore(tmp_path / "offset.json"),
        )
        await bridge.handle_update(update(1, f"/pair {start.code}"))
        assert "geçersiz" in api.sent[-1][1]  # PWA kodu Telegram'da geçmez (kanal ayrımı korunur)
        await bridge.handle_update(update(2, f"/pair {start.telegram_code}"))
        assert "Kod alındı" in api.sent[-1][1]
        before = RemoteControlSnapshot(True, "", 0, "", 0.0)
        waiting = await host.snapshot()
        assert waiting.awaiting_device == "Telegram emirhan"  # Telegram kodu hep elle onaylanır
        assert host.changes(before, waiting) == [
            "Telegram emirhan kodu girdi; onay bekliyor (`onayla`)."
        ]
        assert await host.approve_pending()
        device = controller._registry.find_external(CHANNEL_TELEGRAM, "42")
        assert device is not None and device.name == "Telegram emirhan"
        assert (await host.snapshot()).awaiting_device == ""
    finally:
        await host.stop()


async def test_kod_yenileme_kanal_basina_eksik_ve_suresi_dolan_kodu_uretir(
    controller: RemoteController,
) -> None:
    host = RemoteControlHost(controller, extra_scopes=("project.write",))
    start = await host.start(port=_free_port(), tunnel=True)
    try:
        assert [c.channel for c in host.codes] == [CHANNEL_REQUEST_PWA]
        assert await host.renew_codes(now=start.expires_at - 1) == []  # vakti gelmemiş kod duruyor
        # Onay bekleyen cihazın kodu, süresi yaklaşsa da yenilenmez (soru askıda kalmasın).
        controller._pairing.submit(start.code, "Tablet")
        assert await host.renew_codes(now=start.expires_at + 1) == []
        assert await host.reject_pending() and host.code == ""
        renewed = await host.renew_codes(now=0.0)
        assert [c.channel for c in renewed] == [CHANNEL_REQUEST_PWA] and host.code == renewed[
            0
        ].code
        assert not await host.reject_pending()  # bekleyen cihaz yokken reddetmek etkisiz
    finally:
        await host.stop()


async def test_baslatma_kod_uretiminde_duserse_sunucu_kapanir(
    controller: RemoteController, monkeypatch: Any
) -> None:
    """Ölçüldü (31 Ekim): `_started=True` sonrası `new_code` hatasında HTTP açık kalıyordu;
    REPL `/rc` host'u saklamadığı için port bir sonraki denemede doluydu."""
    host = RemoteControlHost(controller)
    original = controller.dispatch

    async def dispatch(name: str, data: dict[str, Any]) -> dict[str, Any]:
        if name == "uzak.eslestir_baslat":
            return {"ok": False, "metin": "kod üretilemedi"}
        return await original(name, data)

    monkeypatch.setattr(controller, "dispatch", dispatch)
    port = _free_port()
    with pytest.raises(RemoteControlError, match="kod üretilemedi"):
        await host.start(port=port, tunnel=True)
    assert not host.started
    status = await original("uzak.durum", {})
    assert status["dinliyor"] is False  # port serbest
    monkeypatch.setattr(controller, "dispatch", original)
    second = RemoteControlHost(controller)
    await second.start(port=port, tunnel=True)  # aynı port yeniden alınır
    await second.stop()


def _unused(_value: Any) -> None:  # tip denetimi için
    return None

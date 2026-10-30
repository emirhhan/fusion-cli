"""İptalde sahipli iş parçacığı beklemesi sınırlıdır; asılan iş "sahipsiz kaldı" olarak bildirilir (C1-15).

Ölçüldü (30 Ekim): iptal döngüsü `CancelledError`'ı yutup iş parçacığı bitene dek bekliyordu;
asılan bir iş parçacığında (ağ okuması, kilit) "durdur" hiç tamamlanmıyordu.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

import pytest

from fusion_cli.core import owned_thread


@pytest.fixture(autouse=True)
def kisa_sinir(monkeypatch):
    monkeypatch.setattr(owned_thread, "OWNED_THREAD_CANCEL_GRACE_S", 0.3)


async def _iptal_et(operation, cancel=None):
    if cancel is None:
        gorev = asyncio.create_task(owned_thread.await_owned_thread(operation))
    else:
        gorev = asyncio.create_task(owned_thread.await_cancellable_thread(operation, cancel))
    await asyncio.sleep(0.1)
    gorev.cancel()
    return gorev


async def test_asilan_is_parcacigi_iptali_sonsuza_dek_tutmaz():
    birak = threading.Event()
    gorev = await _iptal_et(lambda: birak.wait(30))
    try:
        basla = time.monotonic()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(gorev, timeout=3)
        assert time.monotonic() - basla < 2
    finally:
        birak.set()


async def test_sahipsiz_kalan_is_olay_ve_sayac_uretir_bitince_sayac_duser(caplog):
    olaylar: list[str] = []
    owned_thread.add_orphan_listener(olaylar.append)
    birak = threading.Event()

    def asili() -> None:
        birak.wait(30)

    try:
        gorev = await _iptal_et(asili)
        with caplog.at_level(logging.ERROR), pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(gorev, timeout=3)
        assert owned_thread.orphaned_thread_count() == 1
        assert olaylar and "asili" in olaylar[0]
        assert any("sahipsiz" in kayit.getMessage() for kayit in caplog.records)
    finally:
        birak.set()
        owned_thread.remove_orphan_listener(olaylar.append)
    for _ in range(50):
        if owned_thread.orphaned_thread_count() == 0:
            break
        await asyncio.sleep(0.05)
    assert owned_thread.orphaned_thread_count() == 0


async def test_zamaninda_biten_is_sahipsiz_sayilmaz_ve_iptal_beklenir():
    bitti = threading.Event()

    def kisa() -> None:
        time.sleep(0.15)
        bitti.set()

    gorev = await _iptal_et(kisa)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(gorev, timeout=3)

    assert bitti.is_set()  # temizlik beklendi
    assert owned_thread.orphaned_thread_count() == 0


async def test_iptal_bildirimi_hala_calisir():
    birak = threading.Event()
    gorev = await _iptal_et(lambda: birak.wait(30), cancel=birak.set)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(gorev, timeout=3)
    assert birak.is_set()
    assert owned_thread.orphaned_thread_count() == 0


async def test_cleanup_failed_hatasi_hala_yukselir():
    from fusion_cli.core.errors import CleanupFailedError

    def kotu() -> None:
        time.sleep(0.15)
        raise CleanupFailedError("temizlenemedi")

    gorev = await _iptal_et(kotu)
    with pytest.raises(CleanupFailedError):
        await asyncio.wait_for(gorev, timeout=3)

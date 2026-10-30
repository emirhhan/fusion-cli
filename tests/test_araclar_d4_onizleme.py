"""Önizleme sunucusu dayanıklılığı (T2-22)."""

from __future__ import annotations

import sys
import time

import pytest

from fusion_cli.tools import preview_server
from fusion_cli.tools.preview_server import PreviewError, PreviewKind


@pytest.fixture(autouse=True)
def _temizle():
    yield
    preview_server.stop_all()


async def test_hemen_olen_surec_45_sn_beklenmez_ve_hata_gosterilir(tmp_path):
    """Süreç çökerse tam SERVER_READY_S beklenip "yanıt vermedi" denmesin; çıktı kuyruğu gelsin."""
    baslangic = time.monotonic()

    with pytest.raises(PreviewError) as hata:
        await preview_server.start(
            tmp_path, PreviewKind.PHP, preview_server.free_port(), php=sys.executable
        )

    assert time.monotonic() - baslangic < 15
    mesaj = str(hata.value)
    assert "çıkış kodu" in mesaj
    assert "display_errors=1" in mesaj  # sürecin kendi hata çıktısı (günlük kuyruğu)


async def test_olen_surec_cagrildiginda_wait_hemen_false_doner():
    class _Olu:
        returncode = 1

    baslangic = time.monotonic()
    sonuc = await preview_server.wait_until_serving(
        "http://127.0.0.1:1/", timeout_s=30, process=_Olu()
    )

    assert sonuc is False
    assert time.monotonic() - baslangic < 3

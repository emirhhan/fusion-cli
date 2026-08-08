"""Senaryo dökümleri üzerinde İDDİA içeren testler.

`tests/scenario.py` dökümü üretir ve elle okunabilir; burası o dökümü regresyona
bağlar. Her iddia gerçek bir koşuda gözlenmiş bir hataya karşılık gelir — hata
tekrar ederse burada kırılır, kullanıcının canlı oturumda görmesine gerek kalmaz.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .scenario import run_scenario
from .scenarios import (
    AYNI_CEVAP_IKI_KEZ,
    GERCEK_IS_YAPAN_TUR,
    IS_YAPMADAN_SORU,
    ROL_BASLIGI_SIZINTISI,
    TUR_ORTASINDA_TESLIM,
    UYDURMA_TESLIM,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path


async def test_ayni_cevap_iki_kez_basilmaz(root):
    run = await run_scenario(AYNI_CEVAP_IKI_KEZ, root)

    ilk_cumle = UYDURMA_TESLIM.split(".")[0]
    assert run.transcript.count(ilk_cumle) <= 1, "aynı cevap birden çok kez basıldı"


async def test_elenmis_cevap_kullaniciya_gosterilmez(root):
    """Kapı bir cevabı reddettiyse kullanıcı onu hiç görmemeli."""
    run = await run_scenario(IS_YAPMADAN_SORU, root)

    assert "Ne yapmak istediğinizi belirtin?" not in run.transcript


async def test_tur_ortasindaki_teslim_raporu_ekrani_kaplamaz(root):
    """Öncü metin tek satıra sığar; dört başlıklı rapor ekrana dökülemez."""
    run = await run_scenario(TUR_ORTASINDA_TESLIM, root)

    assert "Kontrol Edilmesi Gerekenler" not in run.transcript
    assert "Ne Yapıldı" not in run.transcript


async def test_oncu_cumle_hala_gorunur(root):
    """Sınırlama öncüyü YOK ETMEZ; kullanıcı turun neden başladığını görmeli."""
    run = await run_scenario(TUR_ORTASINDA_TESLIM, root)

    assert "Bağlı projeleri arıyorum." in run.transcript


async def test_rol_basligi_dokume_sizmaz(root):
    run = await run_scenario(ROL_BASLIGI_SIZINTISI, root)

    assert "FUSION//" not in run.transcript


async def test_kanitsiz_teslim_basari_olarak_kapanmaz(root):
    run = await run_scenario(AYNI_CEVAP_IKI_KEZ, root)

    assert run.outcome.ok is False
    assert run.outcome.made_no_changes is True


async def test_referans_tur_temiz_akar(root):
    """Doğru davranışın dökümü: öncü, diff, tek kapanış, rozet yok."""
    run = await run_scenario(GERCEK_IS_YAPAN_TUR, root)

    assert run.outcome.ok is True
    assert run.outcome.mutating_tool_calls_made == 1
    assert run.outcome.made_no_changes is False
    assert "Mevcut betikleri görmek için dosyayı okuyorum." in run.transcript
    assert "lint" in run.transcript
    kapanis = "`package.json` içine `lint` betiği eklendi"
    assert run.transcript.count(kapanis) == 1, "nihai cevap tam olarak bir kez basılmalı"
    assert "değiştirilmedi" not in run.transcript

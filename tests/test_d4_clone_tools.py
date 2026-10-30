"""Site kopyalama yardımcıları: fiyat biçimi, kategori, yedek, sessiz hata (A1-35..A1-39)."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent import clone_tools
from fusion_cli.engines.agent.clone_tools import (
    _backup_theme,
    _localize_store,
    category_labels,
    price_format,
)


@pytest.mark.parametrize(
    ("ornek", "binlik", "ondalik", "konum"),
    [
        ("7.199,00 TL", ".", ",", "right_space"),
        ("7.199 TL", ".", ",", "right_space"),
        ("199,90 TL", ".", ",", "right_space"),
        ("$1,234.56", ",", ".", "left"),
        ("$19.99", ",", ".", "left"),
    ],
)
def test_fiyat_bicimi_tek_ayracli_orneklerde_de_cikarilir(ornek, binlik, ondalik, konum):
    bicim = price_format(ornek)
    assert bicim is not None
    assert (bicim.thousand, bicim.decimal, bicim.position) == (binlik, ondalik, konum)


def test_fiyat_olmayan_metinde_bicim_yok():
    assert price_format("Ücretsiz kargo") is None


@pytest.mark.parametrize("href", ["https://x.com/canta", "https://x.com/%C3%A7anta/", "/ÇANTA"])
def test_turkce_harfli_kategori_adres_parcasiyla_eslesir(href):
    menu = [{"href": href, "text": "ÇANTA"}]

    assert category_labels(menu, ("çanta",), "tr") == {"çanta": "Çanta"}


def test_tema_yedegi_alt_klasorleri_de_kapsar(tmp_path):
    tema = tmp_path / "tema"
    (tema / "template-parts").mkdir(parents=True)
    (tema / "assets" / "css").mkdir(parents=True)
    (tema / "header.php").write_text("<?php")
    (tema / "template-parts" / "kart.php").write_text("<?php")
    (tema / "assets" / "css" / "a.css").write_text("a{}")
    (tema / "assets" / "logo.png").write_bytes(b"x")

    hedef = tmp_path / "yedek"
    _backup_theme(tema, hedef)

    yedeklenen = {p.relative_to(hedef).as_posix() for p in hedef.rglob("*") if p.is_file()}
    assert yedeklenen == {"header.php", "template-parts/kart.php", "assets/css/a.css"}


async def test_basarisiz_wp_adimlari_ozette_uyari_olur(tmp_path, monkeypatch):
    async def _hep_basarisiz(wp_cli, root, *args):
        return 1, "hata"

    monkeypatch.setattr(clone_tools, "run_wp", _hep_basarisiz)
    adimlar: list[str] = []

    await _localize_store(tmp_path, "wp", "199,90 TL", "tr-TR", adimlar)

    uyari = [a for a in adimlar if a.startswith("UYARI")]
    assert uyari and "site dili" in uyari[0] and "woocommerce_price_decimal_sep" in uyari[0]


async def test_basarili_wp_adimlarinda_uyari_yok(tmp_path, monkeypatch):
    async def _hep_basarili(wp_cli, root, *args):
        return 0, ""

    monkeypatch.setattr(clone_tools, "run_wp", _hep_basarili)
    adimlar: list[str] = []

    await _localize_store(tmp_path, "wp", "199,90 TL", "tr-TR", adimlar)

    assert not any(a.startswith("UYARI") for a in adimlar)


def test_klon_ozeti_ve_aciklamasi_telif_uyarisi_tasir():
    """A1-38: üçüncü taraf içeriği indirilirken sorumluluk uyarısı sessiz geçmez."""
    from fusion_cli.engines.agent.clone_tools import COPYRIGHT_NOTICE
    from fusion_cli.engines.agent.clone_tools import clone_tools as arac_listesi

    (arac,) = arac_listesi()
    assert "telif" in arac.description.lower() and "izni" in arac.description.lower()
    uyari = COPYRIGHT_NOTICE.format(host="ornek.com")
    assert "ornek.com" in uyari and "iznin" in uyari


def test_klon_ozetinin_ilk_satiri_kaynak_alan_adini_ve_uyariyi_icerir(tmp_path):
    from .test_capture_provenance import _fixture

    capture, theme = _fixture(tmp_path, responsive=False)

    ozet = clone_tools._summary(
        capture, theme, [], [], tmp_path, "https://www.ornek-magaza.com/urunler"
    )

    ilk_satir = ozet.splitlines()[0]
    assert "TELİF/MARKA UYARISI" in ilk_satir and "www.ornek-magaza.com" in ilk_satir

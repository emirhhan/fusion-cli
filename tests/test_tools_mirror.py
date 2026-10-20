"""Site aynalamanın saf mantığı — ağ ve tarayıcı olmadan.

Yol türetme, kaynak seçimi ve bağlantı yeniden yazma burada sınanır. Playwright
tarafı ince bir katmandır ve gerçek siteyle elle doğrulanmıştır (bkz. commit).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.tools.mirror import (
    MAX_ASSETS,
    MirroredAsset,
    asset_local_path,
    is_mirrorable,
    mirror_summary,
    rewrite_links,
)

# --------------------------------------------------------------------------- #
# Yerel yol türetme
# --------------------------------------------------------------------------- #


def test_yerel_yol_assets_altina_duser_ve_uzantiyi_korur():
    yol = asset_local_path("https://cdn.example.com/tema/style.css")
    assert yol.startswith("assets/")
    assert yol.endswith(".css")
    assert "style" in yol


def test_ayni_adres_her_zaman_ayni_yola_duser():
    adres = "https://cdn.example.com/a/style.css"
    assert asset_local_path(adres) == asset_local_path(adres)


def test_ayni_adli_farkli_kaynaklar_carpismaz():
    """İki CDN'den gelen style.css aynı dosyaya yazılamaz."""
    bir = asset_local_path("https://bir.example.com/style.css")
    iki = asset_local_path("https://iki.example.com/style.css")
    assert bir != iki


def test_sorgu_dizesi_farkli_kaynak_sayilir():
    assert asset_local_path("https://x.test/a.js?v=1") != asset_local_path(
        "https://x.test/a.js?v=2"
    )


def test_yol_gezinme_karakterleri_temizlenir():
    """Uzak ad yerel yolu KÖKÜN dışına taşıyamaz."""
    yol = asset_local_path("https://x.test/..%2F..%2Fetc%2Fpasswd")
    assert ".." not in yol
    assert "/" not in yol.removeprefix("assets/")


def test_uzantisiz_kaynak_da_ad_alir():
    yol = asset_local_path("https://x.test/fontlar/gizli")
    assert yol.startswith("assets/") and len(yol) > len("assets/")


def test_bos_yollu_adres_ad_uydurur():
    assert asset_local_path("https://x.test/").startswith("assets/")


# --------------------------------------------------------------------------- #
# Hangi kaynak aynalanır
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "https://x.test/a.css",
        "https://x.test/a.js",
        "https://x.test/a.png",
        "https://x.test/a.woff2",
        "https://x.test/a.svg",
    ],
)
def test_bilinen_uzantilar_aynalanir(url):
    assert is_mirrorable(url) is True


def test_sorgu_dizesi_uzantiyi_gizlese_de_icerik_turu_karar_verir():
    assert is_mirrorable("https://x.test/asset?id=9", "text/css; charset=utf-8") is True


def test_html_aynalanmaz():
    """Sayfanın kendisi ayrıca yazılır; kaynak olarak indirilmez."""
    assert is_mirrorable("https://x.test/sayfa.html") is False


def test_veri_uri_aynalanmaz():
    assert is_mirrorable("data:image/svg+xml,%3Csvg/%3E", "image/svg+xml") is False


def test_bilinmeyen_tur_aynalanmaz():
    assert is_mirrorable("https://x.test/veri", "application/json") is False


# --------------------------------------------------------------------------- #
# Bağlantı yeniden yazma
# --------------------------------------------------------------------------- #


def test_mutlak_adres_yerel_yolla_degistirilir():
    asset = MirroredAsset(url="https://cdn.test/a.css", local="assets/a-123.css")
    html = '<link href="https://cdn.test/a.css">'
    assert rewrite_links(html, (asset,)) == '<link href="assets/a-123.css">'


def test_semasiz_adres_de_degistirilir():
    asset = MirroredAsset(url="https://cdn.test/a.css", local="assets/a-123.css")
    assert "assets/a-123.css" in rewrite_links('<link href="//cdn.test/a.css">', (asset,))


def test_koke_goreli_adres_de_degistirilir():
    asset = MirroredAsset(url="https://cdn.test/a.css", local="assets/a-123.css")
    assert "assets/a-123.css" in rewrite_links('<link href="/a.css">', (asset,))


def test_uzun_adres_kisa_adresten_once_degistirilir():
    """`/a.css` ile `/a.css.map` — kısası önce uygulanırsa uzununu bozar."""
    kisa = MirroredAsset(url="https://cdn.test/a.css", local="assets/a-1.css")
    uzun = MirroredAsset(url="https://cdn.test/a.css.map", local="assets/a-2.map")
    sonuc = rewrite_links('<x a="/a.css" b="/a.css.map">', (kisa, uzun))
    assert 'b="assets/a-2.map"' in sonuc
    assert 'a="assets/a-1.css"' in sonuc


def test_yakalanmamis_adres_dokunulmadan_kalir():
    html = '<script src="https://analitik.test/t.js"></script>'
    assert rewrite_links(html, ()) == html


def test_sorgu_dizeli_adres_sorgusuyla_birlikte_degistirilir():
    asset = MirroredAsset(url="https://cdn.test/a.js?v=7", local="assets/a-9.js")
    assert "assets/a-9.js" in rewrite_links('<script src="/a.js?v=7">', (asset,))


# --------------------------------------------------------------------------- #
# Özet — modelin "eksiksiz kopyaladım" demesini engelleyen metin
# --------------------------------------------------------------------------- #


def test_ozet_sinirlari_acikca_yazar(tmp_path: Path):
    ayna = (MirroredAsset("https://x.test/a.css", "assets/a.css"),)
    ozet = mirror_summary(tmp_path, ayna, 0, False)
    assert "SUNMA" in ozet
    assert "diğer sayfaları indirilmedi" in ozet
    assert "ÇALIŞMAZ" in ozet


def test_ozet_kaynak_ve_atlanan_sayisini_bildirir(tmp_path: Path):
    ayna = (MirroredAsset("https://x.test/a.css", "assets/a.css"),)
    ozet = mirror_summary(tmp_path, ayna, 3, False)
    assert "1 kaynak" in ozet
    assert "atlanan: 3" in ozet


def test_ozet_sinira_dayanildigini_bildirir(tmp_path: Path):
    ozet = mirror_summary(tmp_path, (), 0, True)
    assert str(MAX_ASSETS) in ozet
    assert "UYARI" in ozet


def test_ozet_sinira_dayanilmadiysa_uyarmaz(tmp_path: Path):
    assert "UYARI" not in mirror_summary(tmp_path, (), 0, False)

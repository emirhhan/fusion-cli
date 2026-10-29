"""`write_theme` mevcut tema dosyalarını sessizce ezmez (T2-03).

Ölçüldü (29 Ekim): `dosyalar` sözlüğü koşulsuz `write_text` ile yazılıyordu; `style.css`
("Elle düzeltmeler buraya" diye davet eden), `functions.php` vb. varsa kullanıcının ya
da modelin düzeltmeleri kayboluyordu. Ayrıca `theme_slug` yalnız ilk alan adı etiketini
aldığı için `shop.example.com` ve `blog.example.com` aynı klasörü paylaşıyordu.
"""

from __future__ import annotations

import hashlib

import pytest

from fusion_cli.tools.site_capture import CapturedPage, SiteCapture
from fusion_cli.tools.woo_theme import PREVIOUS_DIR, theme_slug, write_theme


def _yakalama(ana: str = "<section>ana</section>") -> SiteCapture:
    sayfa = CapturedPage(
        url="https://www.ornek.com",
        title="Örnek",
        lang="tr",
        body_class="ana",
        header="<header>ust</header>",
        main=ana,
        footer="<footer>alt</footer>",
        header_offset=0,
        screenshots={1440: b"jpg"},
    )
    return SiteCapture(pages=(sayfa,), css="body{}", assets={})


def test_elle_duzeltilmis_dosya_yeniden_yazimda_yedeklenir(tmp_path):
    write_theme(_yakalama(), tmp_path, "https://www.ornek.com")
    stil = tmp_path / "ornek-kopya" / "style.css"
    duzeltilmis = stil.read_text(encoding="utf-8") + "\n.benim-duzeltmem{color:red}\n"
    stil.write_text(duzeltilmis, encoding="utf-8")

    sonuc = write_theme(_yakalama(), tmp_path, "https://www.ornek.com")

    sha = hashlib.sha256(duzeltilmis.encode()).hexdigest()[:8]
    yedek = tmp_path / "ornek-kopya" / PREVIOUS_DIR / f"style.css.{sha}"
    assert yedek.read_text(encoding="utf-8") == duzeltilmis
    assert any("style.css" in satir and PREVIOUS_DIR in satir for satir in sonuc.problems)


def test_degismemis_dosya_yedeklenmez(tmp_path):
    write_theme(_yakalama(), tmp_path, "https://www.ornek.com")

    sonuc = write_theme(_yakalama(), tmp_path, "https://www.ornek.com")

    assert not (tmp_path / "ornek-kopya" / PREVIOUS_DIR).exists()
    assert not any(PREVIOUS_DIR in satir for satir in sonuc.problems)


def test_yeni_icerik_yedekten_bagimsiz_yazilir(tmp_path):
    write_theme(_yakalama("<section>bir</section>"), tmp_path, "https://www.ornek.com")

    write_theme(_yakalama("<section>iki</section>"), tmp_path, "https://www.ornek.com")

    onsayfa = (tmp_path / "ornek-kopya" / "front-page.php").read_text(encoding="utf-8")
    assert "iki" in onsayfa and "bir" not in onsayfa


@pytest.mark.parametrize(
    ("adres", "beklenen"),
    [
        ("https://www.sneaksup.com/erkek", "sneaksup-kopya"),
        ("https://sneaksup.com", "sneaksup-kopya"),
        ("https://shop.example.com", "shop-example-com-kopya"),
        ("https://blog.example.com", "blog-example-com-kopya"),
        ("https://www.foo.co.uk", "foo-co-uk-kopya"),
        ("http://localhost:8080", "localhost-kopya"),
    ],
)
def test_farkli_alt_alan_adlari_ayri_klasor_alir(adres, beklenen):
    assert theme_slug(adres) == beklenen

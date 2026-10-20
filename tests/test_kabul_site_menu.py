"""Menü kabulü yanlış paneli ve görünmeyen içeriği başarı saymaz."""

from __future__ import annotations

import pytest
from evals.kabul.areas import site_clone_menu as menu


def test_ayni_sayida_yanlis_menu_acilmasi_kalir():
    kaynak = (menu.MenuPanel("Kadın", ("Sneaker",)),)
    kopya = (menu.MenuPanel("Erkek", ("Sneaker",)),)
    assert not menu.menu_check(kopya, kaynak).passed


def test_dogru_menu_altinda_yanlis_icerik_kalir():
    kaynak = (menu.MenuPanel("Kadın", ("Sneaker", "Bot")),)
    kopya = (menu.MenuPanel("Kadın", ("Sneaker", "Terlik")),)
    sonuc = menu.menu_check(kopya, kaynak)
    assert not sonuc.passed
    assert "Bot" in sonuc.detail


def test_menu_sirasi_ve_bosluk_farki_kusur_degil():
    kaynak = (menu.MenuPanel("Kadın", ("Sneaker", "Bot")),)
    kopya = (menu.MenuPanel(" Kadın  ", (" Bot ", "Sneaker")),)
    assert menu.menu_check(kopya, kaynak).passed


def test_kaynak_olculmediyse_menu_basari_sayilmaz():
    assert not menu.menu_check((), None).passed
    assert menu.menu_check((), ()).passed


@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            yield browser.new_page(viewport={"width": 1440, "height": 900})
        finally:
            browser.close()


def test_logo_ilk_uc_baglantiyi_tuketse_de_menu_olculur(page):
    page.set_content("""<style>
      .panel {display:none} .group:hover .panel {display:block}
      .panel a {display:block}
      </style><header>
      <a href="#">Logo</a><a href="#">Hesap</a><a href="#">Destek</a>
      <div class="group"><a href="#">Kadın</a><div class="panel">
      <a href="/sneaker">Sneaker</a><a href="/bot">Bot</a>
      </div></div></header>""")
    assert menu.menu_panels_opened(page) == (menu.MenuPanel("Kadın", ("Sneaker", "Bot")),)


def test_gizli_atanin_baglantilari_acik_panel_sayilmaz(page):
    page.set_content("""<style>
      .panel {visibility:hidden} .group:hover .panel {visibility:visible}
      .invisible {opacity:0} .panel a {display:block}
      </style><header><div class="group"><a href="#">Kadın</a>
      <div class="panel"><a href="/sneaker">Sneaker</a>
      <div class="invisible"><a href="/bot">Bot</a></div></div>
      </div></header>""")
    assert menu.menu_panels_opened(page) == (menu.MenuPanel("Kadın", ("Sneaker",)),)


def test_menu_acilmiyorsa_baglantilar_olculmez(page):
    page.set_content('<header><a href="/kadin">Kadın</a></header>')
    assert menu.menu_panels_opened(page) == ()


def test_sifir_yukseklikle_kirpilan_panel_acilinca_olculur(page):
    page.set_content("""<style>
      .panel {max-height:0;overflow:hidden}
      .group:hover .panel {max-height:200px} .panel a {display:block}
      </style><header><div class="group"><a href="#">Kadın</a>
      <div class="panel"><a href="/sneaker">Sneaker</a>
      <a href="/bot">Bot</a></div></div></header>""")
    assert menu.menu_panels_opened(page) == (menu.MenuPanel("Kadın", ("Sneaker", "Bot")),)

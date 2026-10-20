"""Tur tarayıcısı gerçek olmalı ama kullanıcının önünde durmamalı.

Ölçüldü (12 Eylül): `headless=True` ile ChatGPT turu 16 saniyede Cloudflare
doğrulamasına takılıyor — profilde geçerli `cf_clearance` olmasına rağmen, çünkü
headless Chrome farklı bir User-Agent gönderir ve çerez o kimliğe bağlıdır.
Yani görünür (headful) Chrome ZORUNLU.

Bunun bedeli kullanıcının ekranında sürekli açılan bir pencereydi. Pencere ekran
DIŞINA alınır: tarayıcı hâlâ gerçek headful Chrome'dur (aynı UA, aynı parmak izi,
çerez geçerli), yalnız görünür alanda durmaz. Bu bir gizlenme tekniği DEĞİLDİR;
sunucuya giden hiçbir şey değişmez.

Arka plana düşen pencerelerin kısılması ayrıca engellenir: macOS örtülü pencerede
zamanlayıcıları yavaşlatır ve tur bütçesi boşa yanardı.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.core.window_mode import WindowMode
from fusion_cli.providers.web_shared_browser import chrome_launch_arguments


def _args(*, headless: bool | WindowMode) -> list[str]:
    return chrome_launch_arguments("/tmp/chrome", Path("/tmp/profil"), headless=headless)


def test_gorunur_kipte_pencere_ekran_disina_alinir():
    args = _args(headless=False)

    konum = [a for a in args if a.startswith("--window-position=")]
    assert konum, "pencere konumu verilmedi; tarayıcı kullanıcının önünde açılır"
    x, y = konum[0].split("=", 1)[1].split(",")
    assert int(x) < 0 and int(y) < 0, konum


def test_arka_plan_kisilmasi_engellenir():
    args = _args(headless=False)

    assert "--disable-backgrounding-occluded-windows" in args
    assert "--disable-renderer-backgrounding" in args


def test_otomasyon_bayragi_hala_yok():
    """Anti-bot atlatma YOKTUR; bu dosyanın ilkesi değişmedi."""
    args = _args(headless=False)

    assert not any("--enable-automation" in a for a in args)
    assert not any("--disable-blink-features" in a for a in args)


def test_headless_kipte_konum_gereksiz():
    args = _args(headless=True)

    assert "--headless=new" in args


def test_gizli_kipte_headless_bayragi_verilmez():
    """Ölçüldü (17 Eylül): headless Chrome Cloudflare doğrulamasını 7 turun 7'sinde geçemedi.

    Gizli kip bu yüzden GERÇEK pencereli Chrome açar; pencereyi bayrak değil,
    açılıştan sonraki işletim sistemi çağrısı gizler.
    """
    args = _args(headless=WindowMode.HIDDEN)

    assert "--headless=new" not in args
    assert not any("--headless" in argument for argument in args)


def test_gizli_kip_de_otomasyon_bayragi_tasimaz():
    """Yapılan tek şey pencereyi ekrandan uzak tutmaktır; parmak izi değişmez."""
    args = _args(headless=WindowMode.HIDDEN)

    assert not any("--enable-automation" in argument for argument in args)
    assert not any("--disable-blink-features" in argument for argument in args)


def test_eski_boolean_cagrilari_ayni_kipleri_verir():
    assert _args(headless=True) == _args(headless=WindowMode.HEADLESS)
    assert _args(headless=False) == _args(headless=WindowMode.VISIBLE)

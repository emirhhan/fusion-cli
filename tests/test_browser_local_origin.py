"""Tarayıcı araçları yalnız kullanıcının yazdığı yerel adrese gider; diğer özel ağ kapalı."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import browser, chrome
from fusion_cli.tools.web import browser_block_reason, loopback_origins_in, url_block_reason


def test_mesajdaki_yerel_adresler_host_port_olarak_cikar():
    text = "http://127.0.0.1:51687/ sitesinde formu doldur, sonra https://LOCALHOST:3000/x bak."

    assert loopback_origins_in(text) == {"127.0.0.1:51687", "localhost:3000"}
    assert loopback_origins_in("http://[::1]:8080/") == {"[::1]:8080"}
    assert loopback_origins_in("https://ornek.com:8080 ve 192.168.1.1:80") == set()
    assert loopback_origins_in("http://127.0.0.1/ portsuz") == set()


def test_izin_verilen_yerel_adres_acilir_digerleri_kapali_kalir():
    allowed = {"127.0.0.1:51687"}

    assert browser_block_reason("http://127.0.0.1:51687/tablo?sayfa=2", allowed) is None
    assert browser_block_reason("http://127.0.0.1:9999/", allowed) is not None
    assert browser_block_reason("http://127.0.0.1:51687/", ()) is not None
    assert browser_block_reason("http://localhost:51687/", allowed) is not None


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.1.1:51687/",
        "http://169.254.169.254:51687/latest/meta-data/",
        "http://10.0.0.5:51687/",
        "file:///etc/passwd",
        "http://127.0.0.1:51687@192.168.1.1/",
    ],
)
def test_izin_listesi_ozel_ag_ve_metadata_adresini_acmaz(url):
    assert browser_block_reason(url, {"127.0.0.1:51687", "192.168.1.1:51687"}) is not None


def test_web_fetch_kapisi_degismedi():
    assert url_block_reason("http://127.0.0.1:51687/") is not None


async def test_tarayici_araclari_izinsiz_yerel_adresi_reddeder(tmp_path):
    context = ToolContext(root=tmp_path)

    opened = await browser.browser_open({"url": "http://127.0.0.1:51687/"}, context)
    navigated = await chrome.chrome_navigate({"url": "http://127.0.0.1:51687/"}, context)

    assert not opened.ok and "erişilemez" in opened.output
    assert not navigated.ok and "erişilemez" in navigated.output


async def test_chrome_izinli_yerel_adreste_adres_kapisini_gecer(tmp_path):
    context = ToolContext(root=tmp_path)
    context.local_origins.add("127.0.0.1:51687")

    result = await chrome.chrome_navigate({"url": "http://127.0.0.1:51687/"}, context)

    # Köprü bağlı değil: hata artık adres kapısından değil, bağlantıdan gelir.
    assert "erişilemez" not in result.output

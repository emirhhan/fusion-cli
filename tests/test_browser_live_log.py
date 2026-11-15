"""Tarayıcı panelinin canlı konsol/ağ toplayıcısı (P-045).

Ölçüldü (31 Ekim, inceleme): toplayıcı tarayıcı ömrü boyunca yaşıyor ve tampon dolunca
(200 konsol, 300 istek) YENİ kayıt almıyordu; `page_log(clear=True)` yeni toplayıcı kurup
dinleyicileri eskisinde bıraktığı için temizlikten sonra hiçbir kayıt gelmiyordu.
"""

from __future__ import annotations

from fusion_cli.core.browser_session import BrowserSession
from fusion_cli.tools.browser_live import LiveView
from fusion_cli.tools.preview_log import (
    MAX_CONSOLE_ENTRIES,
    MAX_NETWORK_ENTRIES,
    PageEventCollector,
)


class _Baglam:
    def __init__(self) -> None:
        self.dinleyiciler: dict[str, list] = {}

    def on(self, olay: str, geri_cagirim) -> None:
        self.dinleyiciler.setdefault(olay, []).append(geri_cagirim)

    def yay(self, olay: str, deger: object) -> None:
        for geri_cagirim in self.dinleyiciler.get(olay, []):
            geri_cagirim(deger)


class _Mesaj:
    def __init__(self, metin: str, tur: str = "error") -> None:
        self.text = metin
        self.type = tur
        self.location: dict[str, object] = {}


class _Istek:
    def __init__(self, url: str) -> None:
        self.url = url
        self.method = "GET"
        self.resource_type = "fetch"


def test_temizledikten_sonra_yeni_konsol_ve_ag_kaydi_gelir():
    canli = LiveView(BrowserSession())
    baglam = _Baglam()
    canli.watch_context(baglam)
    baglam.yay("console", _Mesaj("eski"))

    eski = canli.page_log(clear=True)
    baglam.yay("console", _Mesaj("yeni-hata"))
    baglam.yay("request", _Istek("http://127.0.0.1:5173/api"))
    yeni = canli.page_log()

    assert [kayit.text for kayit in eski.console] == ["eski"]
    assert [kayit.text for kayit in yeni.console] == ["yeni-hata"]
    assert [kayit.url for kayit in yeni.requests] == ["http://127.0.0.1:5173/api"]
    canli.watch_context(baglam)  # aynı bağlam ikinci kez dinlenmez: kayıt çiftlenmez
    baglam.yay("console", _Mesaj("tek"))
    assert [kayit.text for kayit in canli.page_log().console].count("tek") == 1


def test_canli_tampon_dolunca_en_yeni_kayitlar_kalir():
    canli = LiveView(BrowserSession())
    baglam = _Baglam()
    canli.watch_context(baglam)
    for sira in range(MAX_CONSOLE_ENTRIES + 5):
        baglam.yay("console", _Mesaj(f"m{sira}"))
    # Playwright istek nesneleri sayfa yaşadıkça yaşar; toplayıcı `id()` ile eşler.
    istekler = [_Istek(f"http://127.0.0.1/{sira}") for sira in range(MAX_NETWORK_ENTRIES + 5)]
    for istek in istekler:
        baglam.yay("request", istek)

    log = canli.page_log()

    assert len(log.console) == MAX_CONSOLE_ENTRIES
    assert log.console[-1].text == f"m{MAX_CONSOLE_ENTRIES + 4}" and log.console[0].text == "m5"
    assert len(log.requests) == MAX_NETWORK_ENTRIES
    assert log.requests[-1].url.endswith(f"/{MAX_NETWORK_ENTRIES + 4}")


def test_tek_seferlik_olcum_ilk_kayitlari_tutar():
    # `onizleme.gunluk` tek sayfa yüklemesidir: ilk hatalar (asıl neden) korunur.
    toplayici = PageEventCollector()
    for sira in range(MAX_CONSOLE_ENTRIES + 5):
        toplayici.console(_Mesaj(f"m{sira}"))  # type: ignore[arg-type]
    assert toplayici.console_entries()[0].text == "m0"
    assert len(toplayici.console_entries()) == MAX_CONSOLE_ENTRIES


async def test_panel_adresi_http_disi_semada_anlasilir_hata_verir():
    # Ölçüldü (31 Ekim, inceleme): `about:blank` → `https://about:blank` olup "Port could not
    # be cast to integer" gibi ham Python mesajı gösteriyordu.
    import pytest

    from fusion_cli.tools.browser_live import LiveInputError

    canli = LiveView(BrowserSession())
    for adres in ("about:blank", "data:text/html,<b>x</b>", "chrome://settings", "file:///etc"):
        with pytest.raises(LiveInputError, match="yalnız http ve https"):
            await canli.checked_url(adres)


async def test_panel_adres_kapisi_olay_dongusunu_bloklamaz(monkeypatch):
    # Ölçüldü (31 Ekim, inceleme): kapı `socket.getaddrinfo`'yu olay döngüsünde çağırıyordu;
    # çözülmeyen alan adında tüm appserver saniyelerce donuyordu.
    import threading

    from fusion_cli.tools import browser_live

    ana = threading.get_ident()
    cagrilar: list[int] = []

    def _kapi(url, origins=()):
        cagrilar.append(threading.get_ident())
        return None

    monkeypatch.setattr(browser_live, "browser_block_reason", _kapi)
    canli = LiveView(BrowserSession())

    assert await canli.checked_url("ornek.dev") == "https://ornek.dev"
    assert await canli.checked_url("localhost:5173") == "http://localhost:5173"
    assert cagrilar and all(kimlik != ana for kimlik in cagrilar)

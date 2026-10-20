"""Çok sayfalı denetim: şablon başına bir sayfa seçimi ve ana sayfaya göre stil tutarlılığı."""

from __future__ import annotations

from fusion_cli.engines.agent.page_audit import (
    StyleSignature,
    consistency_findings,
    pick_audit_pages,
    signature_from,
)

ANA = "http://127.0.0.1:8080/"


def test_her_sablon_turunden_bir_sayfa_secilir():
    links = [
        ANA,
        "http://127.0.0.1:8080/#ust",
        "http://127.0.0.1:8080/urun/kirmizi-kask/",
        "http://127.0.0.1:8080/urun/mavi-kask/",
        "http://127.0.0.1:8080/magaza/",
        "http://127.0.0.1:8080/magaza/page/2/",
        "http://127.0.0.1:8080/sepet/",
        "http://127.0.0.1:8080/odeme/",
        "http://127.0.0.1:8080/hesabim/",
    ]

    secilen = pick_audit_pages(ANA, links, limit=4)

    assert secilen == [
        "http://127.0.0.1:8080/urun/kirmizi-kask/",
        "http://127.0.0.1:8080/magaza/",
        "http://127.0.0.1:8080/sepet/",
        "http://127.0.0.1:8080/odeme/",
    ]


def test_ana_sayfa_capa_ve_gecersiz_adres_secilmez():
    assert pick_audit_pages(ANA, [ANA, "http://127.0.0.1:8080/#a", "mailto:x@y", ""]) == []


def test_ic_sayfa_varsayilan_mavi_baglanti_ve_yazi_tipi_tasiyorsa_engelleyici():
    ana = StyleSignature(font="Inter, sans-serif", content_links=20, default_blue_links=0)
    magaza = StyleSignature(font="Times", content_links=16, default_blue_links=16)
    sepet = StyleSignature(font="Inter, sans-serif", content_links=4, default_blue_links=0)

    engel, uyari = consistency_findings([("/", ana), ("/magaza/", magaza), ("/sepet/", sepet)])

    assert len(engel) == 2 and all("/magaza/" in bulgu for bulgu in engel)
    assert uyari == []


def test_ana_sayfa_da_varsayilan_kullaniyorsa_tasarim_tercihidir_bulgu_yok():
    ana = StyleSignature(font="Times", content_links=10, default_blue_links=10)
    ic = StyleSignature(font="Times", content_links=10, default_blue_links=10)

    assert consistency_findings([("/", ana), ("/hakkinda/", ic)]) == ([], [])


def test_az_baglantili_sayfada_oran_hesaplanmaz():
    ana = StyleSignature(font="Inter", content_links=10)
    ic = StyleSignature(font="Inter", content_links=2, default_blue_links=2)

    assert consistency_findings([("/", ana), ("/x/", ic)]) == ([], [])


def test_sistem_dugmesi_uyari_olur():
    ana = StyleSignature(font="Inter", buttons=4)
    ic = StyleSignature(font="Inter", buttons=3, default_buttons=2)

    engel, uyari = consistency_findings([("/", ana), ("/form/", ic)])

    assert engel == [] and len(uyari) == 1 and "gri sistem düğmesi" in uyari[0]


def test_tarayici_verisi_imzaya_cevrilir_bozuk_veri_bos_imza():
    imza = signature_from(
        {"font": '"Inter", sans-serif', "contentLinks": 8, "defaultBlueLinks": 5.0, "x": 1}
    )

    assert imza.primary_font == "inter" and imza.default_links
    assert signature_from(None) == StyleSignature()
    assert signature_from({"contentLinks": "çok", "buttons": True}) == StyleSignature()
    assert consistency_findings([("/", imza)]) == ([], [])


def test_buzulen_gorsel_oruntusu_engelleyici_tek_gorsel_uyari():
    from fusion_cli.engines.agent.page_audit import shrunk_findings

    oruntu = [("div.swiper-slide", 62, 250)] * 3
    engel, uyari = shrunk_findings("/", oruntu)
    tek_engel, tek_uyari = shrunk_findings("/", [("div.kart", 60, 300)])

    assert len(engel) == 1 and uyari == [] and "62px/250px" in engel[0]
    assert tek_engel == [] and len(tek_uyari) == 1
    assert shrunk_findings("/", []) == ([], [])


_BUZULMUS_SAYFA = """<!doctype html><html><body style="font-family: Arial">
<div style="display:flex;width:900px">
  <div style="width:250px;flex:none"><div style="max-width:25%">
    <img style="width:100%" src="{img}"></div></div>
  <div style="width:250px;flex:none"><div style="max-width:25%">
    <img style="width:100%" src="{img}"></div></div>
  <div style="width:250px;flex:none"><img style="width:100%" src="{img}"></div>
  <img style="width:40px;border-radius:50%" src="{img}">
</div>
<main><a href="/a">Birinci ürün</a> <a href="/b">İkinci ürün</a></main>
<button>Gönder</button></body></html>"""


def test_tarayicida_buzulen_gorsel_ve_stil_imzasi_olculur(tmp_path):
    import base64
    import struct
    import zlib

    import pytest

    playwright = pytest.importorskip("playwright.sync_api")
    from fusion_cli.engines.agent.page_audit import AUDIT_PROBE

    def png(genislik: int) -> str:
        satir = b"\x00" + b"\x80\x80\x80" * genislik
        veri = zlib.compress(satir * 10)
        parca = lambda tur, icerik: (  # noqa: E731
            struct.pack(">I", len(icerik))
            + tur
            + icerik
            + struct.pack(">I", zlib.crc32(tur + icerik) & 0xFFFFFFFF)
        )
        ham = (
            b"\x89PNG\r\n\x1a\n"
            + parca(b"IHDR", struct.pack(">IIBBBBB", genislik, 10, 8, 2, 0, 0, 0))
            + parca(b"IDAT", veri)
            + parca(b"IEND", b"")
        )
        return "data:image/png;base64," + base64.b64encode(ham).decode()

    sayfa = tmp_path / "index.html"
    sayfa.write_text(_BUZULMUS_SAYFA.format(img=png(600)), encoding="utf-8")
    try:
        with playwright.sync_playwright() as p:
            tarayici = p.chromium.launch()
            page = tarayici.new_page(viewport={"width": 1000, "height": 600})
            page.goto(sayfa.as_uri())
            sonuc = page.evaluate(AUDIT_PROBE)
            tarayici.close()
    except playwright.Error as hata:
        pytest.skip(f"tarayıcı yok: {hata}")

    assert len(sonuc["shrunkMedia"]) == 2
    imza = signature_from(sonuc["style"])
    assert imza.primary_font == "arial" and imza.content_links == 2
    assert imza.default_blue_links == 2 and imza.buttons == 1

"""Chrome eklentisinin sayfa içi kodu (`pageAction`) GERÇEK Chromium'da.

Python birim testleri eklentinin DOM mantığını hiç görmüyordu; seçici bayatlaması,
shadow DOM ve iframe gibi hatalar ancak kullanıcının tarayıcısında ortaya çıkıyordu.
Bu set `chrome-extension/core.js` içindeki fonksiyonun KENDİSİNİ yerel test
sayfalarına enjekte eder (ağ yok: istekler `page.route` ile karşılanır).
Playwright Chromium'u kurulu değilse atlanır.
"""

from __future__ import annotations

import base64
import json
import re
import struct
import zlib
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")

_CORE = Path(__file__).resolve().parents[1] / "chrome-extension" / "core.js"


def _png(genislik: int, yukseklik: int) -> bytes:
    """Gerçek ölçülü geçerli PNG (Pillow'suz, stdlib ile)."""
    satirlar = b"".join(b"\x00" + b"\xc8\x28\x28" * genislik for _ in range(yukseklik))

    def _parca(tur: bytes, veri: bytes) -> bytes:
        crc = zlib.crc32(tur + veri) & 0xFFFFFFFF
        return struct.pack(">I", len(veri)) + tur + veri + struct.pack(">I", crc)

    baslik = struct.pack(">IIBBBBB", genislik, yukseklik, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _parca(b"IHDR", baslik)
        + _parca(b"IDAT", zlib.compress(satirlar))
        + _parca(b"IEND", b"")
    )


_PNG = _png(64, 48)


def _page_action_source() -> str:
    metin = _CORE.read_text(encoding="utf-8")
    eslesme = re.search(
        r"export function pageAction\(.*?\n}\n(?=\nexport async function getSelected)", metin, re.S
    )
    assert eslesme, "pageAction core.js içinde bulunamadı"
    return eslesme.group(0).removeprefix("export ")


_SAYFA = """
<!doctype html><html><head><meta charset="utf-8"><title>Test</title>
<meta property="og:image" content="/og.png"></head>
<body>
  <h1>Mağaza</h1>
  <button id="sayac" onclick="this.textContent='Tıklandı'">Sepete ekle</button>
  <button id="bos">Hiçbir şey yapmaz</button>
  <input id="ad" aria-label="Ad soyad">
  <input type="password" aria-label="Parola">
  <div contenteditable="true" aria-label="Not"></div>
  <select aria-label="Beden"><option value="s">S</option><option value="m">M</option></select>
  <input type="file" aria-label="Görsel yükle">
  <button style="display:none">Gizli düğme</button>
  <img src="/urun.png" alt="Ürün">
  <div style="background-image:url('/arka.png');width:10px;height:10px"></div>
  <web-kart></web-kart>
  <iframe srcdoc="<button>Çerçevedeki düğme</button>"></iframe>
  <script>
    customElements.define('web-kart', class extends HTMLElement {
      constructor(){
        super();
        this.attachShadow({mode:'open'}).innerHTML='<button>Gölge düğme</button>';
      }
    });
  </script>
</body></html>
"""


@pytest.fixture(scope="module")
def tarayici():
    with playwright_sync.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as error:  # Chromium ikilisi kurulu değil
            pytest.skip(f"Playwright Chromium başlatılamadı: {error}")
        yield browser
        browser.close()


@pytest.fixture
def sayfa(tarayici):
    page = tarayici.new_page()

    def _karsila(route):
        url = route.request.url
        if url.endswith(".png"):
            route.fulfill(body=_PNG, content_type="image/png")
        else:
            route.fulfill(body=_SAYFA, content_type="text/html; charset=utf-8")

    page.route("http://magaza.test/**", _karsila)
    page.goto("http://magaza.test/")
    page.wait_for_function("document.querySelector('iframe').contentDocument?.body?.innerHTML")
    kaynak = _page_action_source()

    def _calistir(islem: str, args: dict | None = None):
        return page.evaluate(f"([o, a]) => ({kaynak})(o, a)", [islem, args or {}])

    page.islem = _calistir
    yield page
    page.close()


def _ref(page, ad: str) -> str:
    sonuc = page.islem("find", {"query": ad})
    assert sonuc["matches"], f"bulunamadı: {ad}"
    return sonuc["matches"][0]["ref"]


def test_snapshot_shadow_dom_ve_iframe_icini_gorur_parola_ve_gizliyi_gormez(sayfa):
    adlar = [oge["name"] for oge in sayfa.islem("snapshot")["elements"]]

    assert "Gölge düğme" in adlar
    assert "Çerçevedeki düğme" in adlar
    assert "Parola" not in adlar
    assert "Gizli düğme" not in adlar


def test_golgedeki_dugmeye_tiklanir(sayfa):
    ref = _ref(sayfa, "Gölge düğme")

    sonuc = sayfa.islem("click", {"ref": ref})

    assert sonuc["clicked"] == ref


def test_tiklama_imzasi_degisikligi_yakalar(sayfa):
    once = sayfa.islem("signature")
    sayfa.islem("click", {"ref": _ref(sayfa, "Sepete ekle")})
    sonra = sayfa.islem("signature")
    sayfa.islem("click", {"ref": _ref(sayfa, "Hiçbir şey yapmaz")})
    bos = sayfa.islem("signature")

    assert json.dumps(once) != json.dumps(sonra)
    # Odak değişir ama sayfa içeriği değişmez; metin uzunluğu ve düğüm sayısı aynı kalır.
    assert bos["text"] == sonra["text"] and bos["nodes"] == sonra["nodes"]


def test_yazma_dogrulanir(sayfa):
    sonuc = sayfa.islem("type", {"ref": _ref(sayfa, "Ad soyad"), "text": "Emir Han"})
    not_alani = sayfa.islem("type", {"ref": _ref(sayfa, "Not"), "text": "Kapıya bırakın"})

    assert sonuc["verified"] is True
    assert not_alani["verified"] is True
    assert sayfa.input_value("#ad") == "Emir Han"


def test_secim_kutusu(sayfa):
    sonuc = sayfa.islem("select", {"ref": _ref(sayfa, "Beden"), "value": "M"})

    assert sonuc["selected"] == "M"


def test_dosya_yukleme_alani_doldurulur(sayfa):
    veri = base64.b64encode(b"merhaba").decode()
    ref = _ref(sayfa, "Görsel yükle")

    sonuc = sayfa.islem(
        "upload", {"ref": ref, "files": [{"name": "a.txt", "mime": "text/plain", "data": veri}]}
    )

    assert sonuc == {"uploaded": ["a.txt"], "count": 1}


def test_yukleme_dosya_alani_olmayan_ogede_reddedilir(sayfa):
    with pytest.raises(playwright_sync.Error, match="dosya seçme alanı değil"):
        sayfa.islem("upload", {"ref": _ref(sayfa, "Ad soyad"), "files": []})


def test_gorsel_varliklari_gercek_olculeriyle_toplanir(sayfa):
    sonuc = sayfa.islem("assets")

    urun = next(gorsel for gorsel in sonuc["images"] if gorsel["src"].endswith("/urun.png"))
    assert (urun["width"], urun["height"]) == (64, 48)
    assert urun["alt"] == "Ürün"
    assert "http://magaza.test/arka.png" in sonuc["backgrounds"]
    assert sonuc["og_image"] == "http://magaza.test/og.png"
    assert sonuc["palette"]["body"]["font"]


def test_tasarim_olcumu_eklentinin_sayfa_kodunda_calisir(sayfa):
    """`site_design` eklenti bağlıyken bu işlemi çağırır: ölçüm kodu pageAction içinde çalışmalı."""
    sonuc = sayfa.islem("design")

    assert sonuc["url"] == "http://magaza.test/" and sonuc["title"] == "Test"
    assert {"fonts", "colors", "scale", "sections", "products", "images"} <= set(sonuc)
    assert any(gorsel["src"].endswith("/urun.png") for gorsel in sonuc["images"])


# --- P-043: erişilebilirlik ağacı ve doğal dilli find ---------------------------------------


def test_agac_rol_ad_ref_ve_girintiyle_doner_golge_ve_cerceveyi_kapsar(sayfa):
    sonuc = sayfa.islem("tree", {"filter": "all"})

    satirlar = sonuc["tree"].split("\n")
    assert sonuc["lines"] == len(satirlar) and sonuc["truncated"] is False
    assert any(s.startswith('heading "Mağaza" level=1') for s in satirlar)
    assert any(re.fullmatch(r'\s*button "Sepete ekle" \[e\d+\]', s) for s in satirlar)
    assert any('textbox "Ad soyad"' in s for s in satirlar)
    assert any('combobox "Beden"' in s and 'value="S"' in s for s in satirlar)
    metin = sonuc["tree"]
    assert "Gölge düğme" in metin and "Çerçevedeki düğme" in metin
    # Parola alanı ve görünmeyen düğme ağaçta yok; metin satırları girintili.
    assert "Parola" not in metin and "Gizli düğme" not in metin
    assert any(s.startswith("  ") for s in satirlar)


def test_agac_etkilesimli_filtresi_derinlik_ve_alt_agac(sayfa):
    etkilesimli = sayfa.islem("tree", {"filter": "interactive"})
    assert all(re.search(r"\[e\d+\]", s) for s in etkilesimli["tree"].split("\n"))
    assert not any(s.lstrip().startswith("text ") for s in etkilesimli["tree"].split("\n"))

    sig = sayfa.islem("tree", {"filter": "all", "depth": 1})
    assert sig["depth"] == 1 and sig["lines"] < etkilesimli["lines"] + 20

    ref = _ref(sayfa, "Beden")
    alt = sayfa.islem("tree", {"filter": "all", "ref": ref})
    assert alt["lines"] >= 1 and 'combobox "Beden"' in alt["tree"]
    # Alt ağaç mevcut ref'leri sıfırlamaz: aynı ref tıklanabilir kalır.
    assert sayfa.islem("click", {"ref": ref})["clicked"] == ref


def test_dogal_dilli_find_rol_ve_sozcukleri_anlar(sayfa):
    dugme = sayfa.islem("find", {"query": "sepete ekle düğmesi"})
    alan = sayfa.islem("find", {"query": "ad soyad alanı"})
    yukle = sayfa.islem("find", {"query": "görsel yükleme alanı"})
    eski = sayfa.islem("find", {"query": "hiçbir şey"})

    assert dugme["matches"][0]["name"] == "Sepete ekle" and dugme["matches"][0]["tag"] == "button"
    assert alan["matches"][0]["name"] == "Ad soyad" and alan["matches"][0]["tag"] == "input"
    # "yükleme" → kök "yükl" eşleşir (Türkçe ek atma).
    assert yukle["matches"][0]["name"] == "Görsel yükle"
    # Eski alt dize davranışı korunur.
    assert eski["matches"][0]["name"] == "Hiçbir şey yapmaz"


def test_rol_sozcugune_esit_sorgu_o_adi_tasiyan_ogeyi_onde_dondurur(sayfa):
    # Ölçüldü (31 Ekim, bağımsız inceleme): "Menü" sorgusunda sözcük kalmıyor, rol menuitem
    # oluyor; sayfada herhangi bir menuitem varsa yedek ad araması hiç çalışmıyor ve "Menü"
    # yazan hamburger düğmesi dönmüyordu. Eski alt dize davranışı doğru sonucu veriyordu.
    sayfa.set_content(
        '<button aria-label="Menü">☰</button>'
        '<div role="menu"><div role="menuitem" tabindex="0">Profil</div>'
        '<div role="menuitem" tabindex="0">Çıkış</div></div>'
        '<button>Select all</button><select aria-label="Beden"><option>S</option></select>'
    )

    menu = sayfa.islem("find", {"query": "Menü"})
    secim = sayfa.islem("find", {"query": "Select"})

    assert menu["matches"][0]["name"] == "Menü"
    # Rol eşleşmeleri (menü öğeleri) listede kalır, ad eşleşmesinin arkasında.
    assert {m["name"] for m in menu["matches"]} >= {"Menü", "Profil", "Çıkış"}
    assert secim["matches"][0]["name"] == "Select all"
    assert any(m["tag"] == "select" for m in secim["matches"])


_MERKEZ = (
    "(s) => { const r = document.querySelector(s).getBoundingClientRect(); "
    "return [r.left + r.width / 2, r.top + r.height / 2]; }"
)
_BAYRAK = (
    "(s) => { window.__olay = null; document.querySelector(s).addEventListener('click', "
    "(e) => { window.__olay = {meta: e.metaKey, shift: e.shiftKey, ctrl: e.ctrlKey, "
    "alt: e.altKey}; }); }"
)


def test_degistirici_tuslu_tiklama_olay_bayraklarini_tasir(sayfa):
    """#431: Claude computer `modifiers` (cmd+shift) tıklama olayına geçer."""
    sayfa.evaluate(_BAYRAK, "#bos")
    sayfa.islem("click", {"ref": _ref(sayfa, "Hiçbir şey yapmaz"), "mods": ["meta", "shift"]})
    assert sayfa.evaluate("window.__olay") == {
        "meta": True,
        "shift": True,
        "ctrl": False,
        "alt": False,
    }
    x, y = sayfa.evaluate(_MERKEZ, "#bos")
    sayfa.islem("click_at", {"x": x, "y": y, "mods": ["ctrl"]})
    assert sayfa.evaluate("window.__olay")["ctrl"] is True


def test_koordinatla_hover_noktadaki_ogeye_gider(sayfa):
    sayfa.evaluate(
        "window.__ustunde = false; document.querySelector('#bos')"
        ".addEventListener('mouseover', () => { window.__ustunde = true; })"
    )
    x, y = sayfa.evaluate(_MERKEZ, "#bos")
    sonuc = sayfa.islem("hover", {"x": x, "y": y})
    assert sayfa.evaluate("window.__ustunde") is True
    assert sonuc["name"] == "Hiçbir şey yapmaz"


def test_baslangic_noktasindan_surukleme(sayfa):
    sayfa.evaluate(
        "window.__iz = []; document.querySelector('#bos').addEventListener('mousedown', "
        "() => window.__iz.push('down')); document.querySelector('#sayac')"
        ".addEventListener('mouseup', () => window.__iz.push('up'))"
    )
    fx, fy = sayfa.evaluate(_MERKEZ, "#bos")
    tx, ty = sayfa.evaluate(_MERKEZ, "#sayac")
    sonuc = sayfa.islem("drag", {"from_x": fx, "from_y": fy, "x": tx, "y": ty})
    assert sayfa.evaluate("window.__iz") == ["down", "up"]
    assert sonuc["name"] == "Hiçbir şey yapmaz"


def test_dosyalar_noktadaki_birakma_alanina_suruklenip_birakilir(sayfa):
    """#431: Claude upload_image coordinate: sürükle-bırak hedefine dosya bırakılır."""
    sayfa.evaluate(
        "window.__birakilan = null; const h = document.querySelector('#bos'); "
        "h.addEventListener('dragover', (e) => e.preventDefault()); "
        "h.addEventListener('drop', (e) => { e.preventDefault(); "
        "window.__birakilan = [...e.dataTransfer.files].map((f) => f.name); })"
    )
    x, y = sayfa.evaluate(_MERKEZ, "#bos")
    veri = base64.b64encode(b"jpeg").decode()
    sonuc = sayfa.islem(
        "upload", {"x": x, "y": y, "files": [{"name": "a.jpg", "mime": "image/jpeg", "data": veri}]}
    )
    assert sayfa.evaluate("window.__birakilan") == ["a.jpg"]
    assert sonuc["dropped"] == ["a.jpg"]

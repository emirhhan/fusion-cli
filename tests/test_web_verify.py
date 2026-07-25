"""Web çıktısı doğrulayıcısı — saf denetim fonksiyonu.

Kontroller GERÇEK bir koşuda ölçülen hatalardan türetildi; spekülatif kural yok.
Her kural "nesnel olarak bozuk" olmalı: gürültülü bir kapı, hiç kapı olmamasından
kötüdür — agent her turda boş yere düzeltme turu açar.
"""

from __future__ import annotations

from fusion_cli.engines.agent.web_verify import inspect_web_output


def _bulgu_var(bulgular: tuple[str, ...], parca: str) -> bool:
    return any(parca.lower() in bulgu.lower() for bulgu in bulgular)


# --- Ölü görsel servisi ------------------------------------------------------ #


def test_olu_gorsel_servisi_yakalanir():
    """via.placeholder.com kapandı; kullanan her sayfa kırık görselle açılır."""
    html = '<img src="https://via.placeholder.com/300x300?text=Robot" alt="Robot">'

    bulgular = inspect_web_output({"index.html": html})

    assert _bulgu_var(bulgular, "via.placeholder.com")
    assert _bulgu_var(bulgular, "data:") or _bulgu_var(bulgular, "svg"), (
        "bulgu ne yapılacağını da söylemeli"
    )


def test_calisan_gorsel_kaynagi_bulgu_uretmez():
    html = '<img src="./gorseller/robot.webp" alt="Robot"><main>x</main>'

    assert not _bulgu_var(inspect_web_output({"index.html": html}), "görsel")


def test_data_uri_gorsel_bulgu_uretmez():
    html = '<img src="data:image/svg+xml;base64,PHN2Zz4=" alt="x"><main>y</main>'

    assert not _bulgu_var(inspect_web_output({"index.html": html}), "görsel")


# --- Boş bağlantı ------------------------------------------------------------ #


def test_bos_baglanti_yakalanir():
    html = "<main>" + '<a href="#">Kurumsal</a>' * 5 + "</main>"

    assert _bulgu_var(inspect_web_output({"index.html": html}), "boş bağlantı")


def test_gercek_capa_baglantisi_bos_sayilmaz():
    """href='#bolum' sayfa içi çapadır; bozuk değildir."""
    html = '<main><a href="#kampanyalar">Kampanyalar</a></main>'

    assert not _bulgu_var(inspect_web_output({"index.html": html}), "boş bağlantı")


# --- Semantic HTML ----------------------------------------------------------- #


def test_main_etiketi_eksikse_bulgu_uretilir():
    html = "<body><header>x</header><section>y</section><footer>z</footer></body>"

    assert _bulgu_var(inspect_web_output({"index.html": html}), "<main>")


def test_main_varsa_bulgu_uretilmez():
    html = "<body><main><section>y</section></main></body>"

    assert not _bulgu_var(inspect_web_output({"index.html": html}), "<main>")


# --- Stil bütünlüğü ---------------------------------------------------------- #


def test_stilsiz_sinif_orani_yuksekse_bulgu_uretilir():
    """HTML büyürken CSS'in takip etmemesi gerçek koşuda %70'e çıkmıştı."""
    html = "<main>" + "".join(f'<div class="kart-{i}">x</div>' for i in range(10)) + "</main>"
    css = ".kart-0 { color: red; }"

    assert _bulgu_var(inspect_web_output({"a.html": html, "a.css": css}), "stil")


def test_stiller_tamsa_bulgu_uretilmez():
    html = '<main><div class="kart">x</div></main>'
    css = ".kart { color: red; }"

    assert not _bulgu_var(inspect_web_output({"a.html": html, "a.css": css}), "stil")


def test_css_hic_yoksa_stil_kontrolu_yapilmaz():
    """Tek dosyalık sayfa ya da inline stil: CSS dosyası olmaması hata değildir."""
    html = '<main><div class="kart">x</div></main>'

    assert not _bulgu_var(inspect_web_output({"a.html": html}), "stil")


# --- Metindeki vaat ile koddaki sabit ---------------------------------------- #


def test_sayfada_vaat_edilen_tutar_kodda_yoksa_bulgu_uretilir():
    """Üst çubuk '2.000 TL üzeri ücretsiz kargo' derken kod 200 kullanıyordu."""
    html = "<main><p>2.000 TL üzeri ücretsiz kargo</p></main>"
    js = "const shipping = subtotal >= 200 ? 0 : 29;"

    bulgular = inspect_web_output({"a.html": html, "a.js": js})

    assert _bulgu_var(bulgular, "2.000") or _bulgu_var(bulgular, "2000")


def test_vaat_edilen_tutar_kodda_varsa_bulgu_uretilmez():
    html = "<main><p>2.000 TL üzeri ücretsiz kargo</p></main>"
    js = "const shipping = subtotal >= 2000 ? 0 : 29;"

    assert not _bulgu_var(inspect_web_output({"a.html": html, "a.js": js}), "2.000")


def test_para_birimsiz_sayi_tutar_sayilmaz():
    """'14 gün içinde iade' bir tutar değildir; kodda 14 aramak saçmadır."""
    html = "<main><p>14 gün içinde kolay iade</p></main>"
    js = "const x = 1;"

    assert not inspect_web_output({"a.html": html, "a.js": js})


def test_js_yoksa_tutar_kontrolu_yapilmaz():
    html = "<main><p>2.000 TL üzeri ücretsiz kargo</p></main>"

    assert not _bulgu_var(inspect_web_output({"a.html": html}), "2.000")


# --- Genel davranış ---------------------------------------------------------- #


def test_web_dosyasi_yoksa_bulgu_uretilmez():
    assert inspect_web_output({"main.py": "print(1)"}) == ()


def test_temiz_sayfa_hic_bulgu_uretmez():
    html = (
        '<body><main><a href="/kurumsal">Kurumsal</a>'
        '<img src="./a.webp" alt="a"><div class="kart">x</div></main></body>'
    )
    css = ".kart { color: red; }"

    assert inspect_web_output({"a.html": html, "a.css": css}) == ()


# --- Tasarım token'ı baypası ------------------------------------------------- #
#
# Gerçek koşuda CSS :root'ta lacivert/turuncu palet tanımlıydı ama ürün kartlarını
# üreten script.js `#2563eb` gibi başka maviler kullanıyordu. Model "belirtilen
# paletle" dedi; palet dosyada duruyordu ama arayüzde kullanılmıyordu.


def test_paletin_disinda_hex_kullanimi_bildirilir():
    css = ":root { --navy: #15345B; --orange: #FF7A00; }\n.btn { background: var(--navy); }"
    js = 'el.innerHTML = `<button style="background:#2563eb">Al</button>`;'

    bulgular = inspect_web_output({"a.html": "<main>x</main>", "a.css": css, "a.js": js})

    assert _bulgu_var(bulgular, "#2563eb")
    assert _bulgu_var(bulgular, "palet")


def test_paletteki_renk_bildirilmez():
    css = ":root { --navy: #15345B; }"
    js = 'el.style.background = "#15345B";'

    assert not _bulgu_var(inspect_web_output({"a.html": "<main>x</main>", "a.css": css,
                                              "a.js": js}), "palet")


def test_notr_gri_ve_siyah_beyaz_bildirilmez():
    """Gri tonlar, gölge ve kenarlık renkleri palet ihlali sayılmaz."""
    css = ":root { --navy: #15345B; }"
    js = 'x = "#ffffff"; y = "#000000"; z = "#e5e7eb"; w = "#6b7280";'

    assert not _bulgu_var(inspect_web_output({"a.html": "<main>x</main>", "a.css": css,
                                              "a.js": js}), "palet")


def test_palet_tanimli_degilse_kontrol_yapilmaz():
    """:root'ta palet yoksa neyin ihlal olduğu bilinemez."""
    js = 'x = "#2563eb";'

    assert not _bulgu_var(inspect_web_output({"a.html": "<main>x</main>", "a.js": js}), "palet")


# --- Üretilen dosya bağlanmış mı --------------------------------------------- #
#
# Gerçek hata: düzeltici tur index.html'i yeniden yazarken <script src="script.js">
# etiketini düşürdü. JS hiç yüklenmedi, tüm dinamik bölümler boş kaldı, konsol
# tertemizdi (çalışan kod yok) ve metin kapısı "temiz" dedi. Sayfa geçerliydi ve boştu.


def test_baglanmamis_js_bildirilir():
    html = "<html><head><link rel=stylesheet href=style.css></head><main>x</main></html>"
    js = "function init(){}"

    bulgular = inspect_web_output({"index.html": html, "script.js": js})

    assert _bulgu_var(bulgular, "script.js")
    assert _bulgu_var(bulgular, "bağlanmamış") or _bulgu_var(bulgular, "yüklenmiyor")


def test_baglanmamis_css_bildirilir():
    html = "<html><head></head><main>x</main><script src=script.js></script></html>"

    bulgular = inspect_web_output({"index.html": html, "style.css": "body{}", "script.js": "x"})

    assert _bulgu_var(bulgular, "style.css")


def test_baglanan_dosyalar_bildirilmez():
    html = (
        "<html><head><link rel=stylesheet href='style.css'></head>"
        "<main>x</main><script src='script.js'></script></html>"
    )

    bulgular = inspect_web_output({"index.html": html, "style.css": "body{}", "script.js": "x"})

    assert not _bulgu_var(bulgular, "bağlanmamış")


def test_alt_dizindeki_referans_da_sayilir():
    html = "<html><main>x</main><script src='./js/script.js'></script></html>"

    assert not _bulgu_var(inspect_web_output({"a.html": html, "script.js": "x"}), "bağlanmamış")


# --- Parça HTML koruması ----------------------------------------------------- #


def test_html_parcasinda_main_aranmaz():
    """Şablon/bileşen parçasında <main> olmaz; orada aramak yanlış pozitiftir."""
    parca = '<div class="kart"><h3>Başlık</h3><p>metin</p></div>'

    assert not _bulgu_var(inspect_web_output({"kart.html": parca}), "<main>")


def test_tam_belgede_main_aranir():
    tam = "<html><head></head><body><section>x</section></body></html>"

    assert _bulgu_var(inspect_web_output({"index.html": tam}), "<main>")


# --- Boşluk ölçeği ----------------------------------------------------------- #
#
# Model boşlukları göz kararı veriyor (13px, 17px, 42px). Referansta 4'ün katlarından
# oluşan bir ölçek var ama tavsiye tavsiyedir; ölçülebilir olan zorunlu kılınabilir.


def test_olcek_disi_bosluk_bildirilir():
    css = ".a { padding: 13px; } .b { margin: 17px 0; } .c { gap: 42px; }"

    bulgular = inspect_web_output({"a.html": "<html><main>x</main></html>", "a.css": css})

    assert _bulgu_var(bulgular, "13px")
    assert _bulgu_var(bulgular, "ölçek") or _bulgu_var(bulgular, "boşluk")


def test_olcekteki_bosluk_bildirilmez():
    css = ".a { padding: 16px 24px; } .b { gap: 8px; } .c { margin-block: 96px; }"

    assert not _bulgu_var(
        inspect_web_output({"a.html": "<html><main>x</main></html>", "a.css": css}), "ölçek"
    )


def test_ince_cizgi_degerleri_bildirilmez():
    """1-2px kenarlık/hairline boşluk sayılmaz."""
    css = ".a { padding: 2px; } .b { margin: 1px; }"

    assert not _bulgu_var(
        inspect_web_output({"a.html": "<html><main>x</main></html>", "a.css": css}), "ölçek"
    )


def test_degisken_ve_gorece_birimler_bildirilmez():
    """var(), rem, %, clamp() ölçek dışı sayılmaz — zaten doğru yaklaşım."""
    css = ".a { padding: var(--space-5); } .b { gap: 1.5rem; } .c { margin: clamp(1rem,2vw,3rem); }"

    assert not _bulgu_var(
        inspect_web_output({"a.html": "<html><main>x</main></html>", "a.css": css}), "ölçek"
    )


def test_olcek_disi_rem_de_bildirilir():
    """Referans yokken model rem kullanıyor; ölçek kuralı orada da geçerli."""
    css = ".a { padding: 1.1rem; }"  # 17.6px

    assert _bulgu_var(
        inspect_web_output({"a.html": "<html><main>x</main></html>", "a.css": css}), "1.1rem"
    )


def test_olcekteki_rem_bildirilmez():
    css = ".a { padding: 1.5rem; } .b { gap: 0.5rem; }"  # 24px, 8px

    assert not _bulgu_var(
        inspect_web_output({"a.html": "<html><main>x</main></html>", "a.css": css}), "ölçek"
    )

"""Web cevabının HTML'den Markdown'a çevrilmesi — saf, ağsız testler."""

from __future__ import annotations

from fusion_cli.providers.web_markdown import html_to_markdown


def test_baslik_ve_paragraf_ayrilir() -> None:
    html = "<h2>Projenin Amacı</h2><p>Bu proje stok takibi yapar.</p>"
    assert html_to_markdown(html) == "## Projenin Amacı\n\nBu proje stok takibi yapar."


def test_yapisi_olmayan_metin_oldugu_gibi_kalir() -> None:
    assert html_to_markdown("Merhaba Emirhan") == "Merhaba Emirhan"


def test_madde_listesi_isaretlenir() -> None:
    html = "<p>Sorunlar:</p><ul><li>fiyat hatalı</li><li>stok düşmüyor</li></ul>"
    assert html_to_markdown(html) == "Sorunlar:\n\n- fiyat hatalı\n- stok düşmüyor"


def test_numarali_liste_sirayi_korur() -> None:
    html = "<ol><li>testleri çalıştır</li><li>hatayı düzelt</li></ol>"
    assert html_to_markdown(html) == "1. testleri çalıştır\n2. hatayı düzelt"


def test_kod_blogu_dil_etiketiyle_cevrilir() -> None:
    html = '<pre><code class="language-python">def topla(a, b):\n    return a + b</code></pre>'
    assert html_to_markdown(html) == "```python\ndef topla(a, b):\n    return a + b\n```"


def test_kod_blogunda_girinti_ve_bosluk_korunur() -> None:
    html = "<pre><code>if x:\n    y = 1\n\n    z = 2</code></pre>"
    assert html_to_markdown(html) == "```\nif x:\n    y = 1\n\n    z = 2\n```"


def test_satir_ici_kod_isaretlenir() -> None:
    html = "<p>Dosya <code>stokapp/fiyat.py</code> düzeltildi.</p>"
    assert html_to_markdown(html) == "Dosya `stokapp/fiyat.py` düzeltildi."


def test_kalin_ve_egik_yazi_korunur() -> None:
    html = "<p><strong>Uyarı:</strong> <em>stok</em> düşmüyor.</p>"
    assert html_to_markdown(html) == "**Uyarı:** *stok* düşmüyor."


def test_tablo_markdown_tablosuna_cevrilir() -> None:
    html = (
        "<table><thead><tr><th>Dosya</th><th>Durum</th></tr></thead>"
        "<tbody><tr><td>fiyat.py</td><td>düzeltildi</td></tr></tbody></table>"
    )
    assert html_to_markdown(html) == (
        "| Dosya | Durum |\n| --- | --- |\n| fiyat.py | düzeltildi |"
    )


def test_bag_adres_ile_yazilir() -> None:
    html = '<p>Kaynak: <a href="https://tcmb.gov.tr">TCMB</a></p>'
    assert html_to_markdown(html) == "Kaynak: [TCMB](https://tcmb.gov.tr)"


def test_alinti_blogu() -> None:
    assert html_to_markdown("<blockquote><p>ölçülmeden karar verilmez</p></blockquote>") == (
        "> ölçülmeden karar verilmez"
    )


def test_kod_blogundan_once_gelen_dil_etiketi_atilir() -> None:
    """Sağlayıcı arayüzü kod bloğunun üstüne dil adını ayrı bir kutuda basıyor.

    Ölçüldü (Gemini web, 17 Eylül): cevaba "Plaintext." satırı karışıyor ve
    bu satır dosya içeriğinin ilk satırı hâline gelebiliyordu.
    """
    html = "<div>Plaintext</div><pre><code>birinci satır</code></pre>"
    assert html_to_markdown(html) == "```\nbirinci satır\n```"


def test_bos_html_bos_doner() -> None:
    assert html_to_markdown("   ") == ""


def test_ardisik_bos_satirlar_sadelesir() -> None:
    html = "<p>bir</p><br><br><br><p>iki</p>"
    assert html_to_markdown(html) == "bir\n\niki"


def test_bozuk_html_metne_dusur() -> None:
    """Ayrıştırılamayan girdi kaybolmaz: en kötü ihtimalle düz metin kalır."""
    assert html_to_markdown("<p>yarım <b>kalın") == "yarım **kalın**"


async def test_yanit_html_ile_gelirse_markdown_okunur() -> None:
    """Gerçek sayfa HTML döndürür; okunan metin yapısını korumalıdır."""
    from fusion_cli.providers.web_browser import _response_snapshot

    class _Locator:
        async def evaluate_all(self, _script: str) -> list[dict[str, str]]:
            return [{"html": "<h3>Özet</h3><ul><li>bir</li></ul>", "text": "ÖzetBir"}]

    class _Page:
        def locator(self, _selector: str) -> _Locator:
            return _Locator()

    assert await _response_snapshot(_Page(), ("dar",)) == ("### Özet\n\n- bir",)


async def test_cevri_icerigi_yutarsa_duz_metne_dusulur() -> None:
    """Beklenmedik DOM'da biçim kaybı kabul edilir, İÇERİK kaybı kabul edilmez."""
    from fusion_cli.providers.web_browser import _response_snapshot

    class _Locator:
        async def evaluate_all(self, _script: str) -> list[dict[str, str]]:
            return [{"html": "<svg><path d='M0 0'/></svg>", "text": "modelin uzun cevabı burada"}]

    class _Page:
        def locator(self, _selector: str) -> _Locator:
            return _Locator()

    assert await _response_snapshot(_Page(), ("dar",)) == ("modelin uzun cevabı burada",)


def test_madde_icinde_blok_varsa_ime_yapisik_kalir() -> None:
    """Sağlayıcı madde içeriğini `div`/`p` ile sarabiliyor.

    Ölçüldü (Gemini web, 17 Eylül): "- " iminden sonra boş satır açılıyor ve
    madde ile içeriği ayrı bloklara düşüyordu.
    """
    html = "<ul><li><p>fiyat hatalı</p></li><li><p>stok düşmüyor</p></li></ul>"
    assert html_to_markdown(html) == "- fiyat hatalı\n- stok düşmüyor"

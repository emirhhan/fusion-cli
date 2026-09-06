"""Mesaj kutusuna yazılan prompt BOZULMADAN yerleşmelidir.

Ölçüldü (6 Eylül canlı koşusu): "hesap/__init__.py, … __init__ ikisini de dışa
aktarsın" isteği editöre "hesap/init.py … init ikisini de dışa aktarsın" olarak
yerleşti; zengin metin editörü `__…__` dizisini kalın metin sanıp alt çizgileri
sildi. Model kendisine söylenen dosyayı sadakatle oluşturdu ve görev üç denemenin
üçünde de düştü — hata modelin değil, teslimatın hatasıydı.

Uzunluk kontrolü bunu göremez: dört karakterlik kayıp %95 eşiğinin çok üstünde
kalır. Bu yüzden markdown'a duyarlı karakterler AYRICA sayılır.
"""

from __future__ import annotations

from fusion_cli.providers.web_browser import markdown_damage


def test_alt_cizgi_yiyen_editor_hasar_olarak_bildirilir():
    yazilan = _UZUN_ISTEK
    yerlesen = "hesap/init.py dosyasını oluştur"

    hasar = markdown_damage(yazilan, yerlesen)

    assert hasar is not None
    assert "4 yazıldı, 0 yerleşti" in hasar


def test_bozulmadan_yerlesen_metin_temiz_sayilir():
    metin = _UZUN_ISTEK

    assert markdown_damage(metin, metin) is None


def test_bosluk_normalizasyonu_hasar_sayilmaz():
    """Editör satır sonu ve boşlukları değiştirir; bu tek başına hasar değildir."""
    yazilan = "ilk satır\n\n__init__.py\n"
    yerlesen = "ilk satır\n__init__.py"

    assert markdown_damage(yazilan, yerlesen) is None


def test_yildiz_ve_ters_tirnak_da_korunur():
    assert markdown_damage("**kalın** ve `kod`", "kalın ve kod") is not None
    assert markdown_damage("a ~~b~~", "a b") is not None


def test_fazla_karakter_hasar_sayilmaz():
    """Editör kendi işaretini eklemiş olabilir; eksilme hasardır, artma değil."""
    assert markdown_damage("a_b", "a_b_") is None


# --------------------------------------------------------------------------- #
# Teslimat akışı: tespit tek başına yetmez, onarım da denenmelidir.
# --------------------------------------------------------------------------- #


#: Gerçek prompt binlerce karakterdir; dört karakterlik kayıp uzunluk eşiğinin
#: (%95) çok üstünde kalır. Test bunu taklit eder, yoksa yanlış kapı tetiklenir.
_UZUN_ISTEK = "hesap/__init__.py dosyasını oluştur. " + "ayrıntı satırı. " * 40


class _Editor:
    """Markdown biçimlendiren sahte mesaj kutusu.

    `fill` ile yazılanı biçimlendirip alt çizgileri yer; yapıştırma olayında
    metni olduğu gibi kabul eder — gerçek zengin metin editörlerinin davranışı.
    """

    def __init__(self, *, paste_repairs: bool) -> None:
        self.content = ""
        self.paste_repairs = paste_repairs
        self.pasted = False

    async def fill(self, text: str) -> None:
        self.content = text.replace("__", "")

    async def evaluate(self, script: str, *args: object) -> object:
        if "innerText" in script:
            return self.content
        self.pasted = True
        if self.paste_repairs and args:
            self.content = str(args[0])
        return None


async def test_bicimlendiren_editor_yapistirma_ile_onarilir():
    from fusion_cli.providers.web_browser import _fill_editor

    editor = _Editor(paste_repairs=True)

    await _fill_editor(editor, _UZUN_ISTEK)

    assert editor.pasted, "hasar görülünce yapıştırma yolu denenmeli"
    assert editor.content == _UZUN_ISTEK


async def test_onarilamayan_bozulma_sessizce_gonderilmez():
    from fusion_cli.providers.web_browser import WebBrowserError, _fill_editor

    editor = _Editor(paste_repairs=False)

    try:
        await _fill_editor(editor, _UZUN_ISTEK)
    except WebBrowserError as hata:
        assert "biçimlendirdi" in str(hata)
    else:
        raise AssertionError("bozulmuş prompt sessizce gönderildi")

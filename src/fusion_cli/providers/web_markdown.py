"""Web sağlayıcının çizdiği cevabı HTML'den Markdown'a çevirir.

Neden var — ölçülmüş bir kayıp (17 Eylül denetimi): cevap sayfadan `innerText` ile
okunuyordu. `innerText` GÖRÜNEN metni verir, YAPIYI vermez: başlık ile paragraf
birbirine yapışır, liste işaretleri kaybolur, tablo tek satıra iner, kod bloğunun
dil etiketi ("Plaintext") içeriğin ilk satırı olur ve çıkarma işareti madde imine
dönüşerek hesabı tersine çevirebilir. Kullanıcı bunu "Fusion bozuk yazıyor" olarak
görüyordu; oysa model doğru yazmıştı.

Saftır: ağ yok, tarayıcı yok, yalnız stdlib. Bozuk/yarım HTML'de de metin kaybolmaz.
"""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

__all__ = ["html_to_markdown"]

#: Başlık seviyeleri.
_BASLIKLAR = {"h1": "#", "h2": "##", "h3": "###", "h4": "####", "h5": "#####", "h6": "######"}
#: Kendi satırında duran ve çevresine boş satır isteyen bloklar.
_BLOKLAR = frozenset({*_BASLIKLAR, "p", "div", "section", "article", "blockquote", "table", "tr"})
#: İçeriği hiç alınmayacak elemanlar (sayfanın kendi süsü).
_ATILAN = frozenset({"script", "style", "button", "svg", "noscript", "template"})
#: Kod bloğunun üstüne sağlayıcının bastığı dil etiketleri; içerik değil süstür.
_DIL_ETIKETLERI = frozenset(
    {
        "plaintext", "text", "python", "bash", "shell", "sh", "json", "yaml", "yml",
        "javascript", "typescript", "html", "css", "sql", "ini", "toml", "gdscript",
        "markdown", "md", "diff", "xml", "java", "go", "rust", "c", "c++", "cpp",
    }
)
#: `class="language-python"` gibi sınıflardan dil adını çıkarır.
_DIL_SINIFI = re.compile(r"(?:language|lang)-([A-Za-z0-9+#]+)")
_UC_VE_FAZLA_BOS_SATIR = re.compile(r"\n{3,}")
#: Satırın sonu bir madde imiyse (- ya da "1. ") blok açılmaz.
_MADDE_IMI_SONU = re.compile(r"(?:^|\n)\s*(?:-|\d+\.) $")


class _MarkdownDonusturucu(HTMLParser):
    """HTML akışını Markdown parçalarına çevirir.

    Ayrıştırıcı akış tabanlıdır: kapanmamış etiketlerde de o ana kadar toplanan
    metin korunur (bkz. `test_bozuk_html_metne_dusur`).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parcalar: list[str] = []
        #: Açık liste yığını: her öğe ("ul", None) ya da ("ol", sıradaki numara).
        self._listeler: list[tuple[str, int]] = []
        #: `pre` içindeyken metin OLDUĞU GİBİ korunur.
        self._pre_derinlik = 0
        self._pre_metin: list[str] = []
        self._pre_dili = ""
        self._alinti_derinlik = 0
        #: Tablo satırı toplanırken hücreler burada birikir.
        self._hucreler: list[str] | None = None
        self._basliktaydi = False
        self._tablo_basligi_yazildi = False
        self._tablo_satiri_yazildi = False
        #: Alıntı bloğunun metni ayrı toplanır; kapanışta her satır "> " alır.
        self._alinti_baslangic: list[int] = []
        #: Kapanmamış satır içi etiketler (bozuk HTML'de kapatmak için).
        self._acik_satirici: list[str] = []
        #: İçeriği atlanan elemanın adı (script/style gibi).
        self._atlanan = ""
        #: Açık bağlantının adresi.
        self._baglanti = ""
        #: Tablo hücresinin metninin başladığı parça indeksi.
        self._hucre_baslangici = 0
        #: Açık madde (`li`) sayısı.
        self._madde_derinlik = 0

    # -- yardımcılar ----------------------------------------------------
    def _yaz(self, metin: str) -> None:
        self._parcalar.append(metin)

    def _blok_ac(self) -> None:
        if not self._parcalar:
            return
        son = "".join(self._parcalar[-2:])
        if son.endswith("\n\n"):
            return
        # Madde iminden hemen sonra blok AÇILMAZ: "- " ile içeriği arasına boş
        # satır girerse madde ikiye bölünür (ölçüldü: Gemini web).
        if _MADDE_IMI_SONU.search(son):
            return
        # Madde İÇİNDE blok kapanışı satır atlatmaz: aynı maddenin paragrafları
        # tek maddede kalmalı, araya boş satır girerse liste bölünür.
        if self._madde_derinlik:
            if not son.endswith((" ", "\n")):
                self._yaz(" ")
            return
        self._yaz("\n\n")

    # -- HTMLParser arayüzü ---------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _ATILAN:
            self._atlanan = tag
            return
        if tag == "pre":
            self._blok_ac()
            self._pre_derinlik += 1
            self._pre_metin = []
            self._pre_dili = ""
            return
        if tag == "code" and self._pre_derinlik:
            self._pre_dili = self._pre_dili or _dil_adi(attrs)
            return
        if tag == "code":
            self._yaz("`")
            return
        if tag in ("strong", "b"):
            self._yaz("**")
            self._acik_satirici.append("**")
            return
        if tag in ("em", "i"):
            self._yaz("*")
            self._acik_satirici.append("*")
            return
        if tag == "a":
            self._yaz("[")
            self._baglanti = dict(attrs).get("href") or ""
            return
        if tag in _BASLIKLAR:
            self._blok_ac()
            self._yaz(f"{_BASLIKLAR[tag]} ")
            return
        if tag in ("ul", "ol"):
            self._blok_ac()
            self._listeler.append((tag, 1))
            return
        if tag == "li":
            if self._parcalar and not "".join(self._parcalar[-1:]).endswith("\n"):
                self._yaz("\n")
            tur, sira = self._listeler[-1] if self._listeler else ("ul", 1)
            girinti = "  " * max(0, len(self._listeler) - 1)
            self._yaz(f"{girinti}{sira}. " if tur == "ol" else f"{girinti}- ")
            self._madde_derinlik += 1
            return
        if tag == "blockquote":
            self._blok_ac()
            self._alinti_derinlik += 1
            self._alinti_baslangic.append(len(self._parcalar))
            return
        if tag == "tr":
            self._hucreler = []
            return
        if tag in ("th", "td"):
            self._basliktaydi = self._basliktaydi or tag == "th"
            self._hucre_baslangici = len(self._parcalar)
            return
        if tag in ("p", "div", "section", "article"):
            self._blok_ac()
            return

    def handle_endtag(self, tag: str) -> None:
        if tag in _ATILAN:
            self._atlanan = ""
            return
        if tag == "pre" and self._pre_derinlik:
            self._pre_derinlik -= 1
            govde = "".join(self._pre_metin).strip("\n")
            self._dil_etiketini_dusur()
            self._blok_ac()
            self._yaz(f"```{self._pre_dili}\n{govde}\n```")
            self._pre_metin = []
            return
        if tag == "code" and not self._pre_derinlik:
            self._yaz("`")
            return
        if tag in ("strong", "b"):
            self._yaz("**")
            if self._acik_satirici and self._acik_satirici[-1] == "**":
                self._acik_satirici.pop()
            return
        if tag in ("em", "i"):
            self._yaz("*")
            if self._acik_satirici and self._acik_satirici[-1] == "*":
                self._acik_satirici.pop()
            return
        if tag == "a":
            adres = self._baglanti
            self._yaz(f"]({adres})" if adres else "]")
            return
        if tag in ("ul", "ol") and self._listeler:
            self._listeler.pop()
            return
        if tag == "li" and self._listeler:
            tur, sira = self._listeler[-1]
            self._listeler[-1] = (tur, sira + 1)
            self._madde_derinlik = max(0, self._madde_derinlik - 1)
            return
        if tag == "blockquote" and self._alinti_derinlik:
            self._alinti_derinlik -= 1
            baslangic = (
                self._alinti_baslangic.pop() if self._alinti_baslangic else len(self._parcalar)
            )
            govde = "".join(self._parcalar[baslangic:]).strip()
            del self._parcalar[baslangic:]
            if govde:
                self._yaz("\n".join(f"> {satir}".rstrip() for satir in govde.split("\n")))
            return
        if tag in ("th", "td") and self._hucreler is not None:
            baslangic = self._hucre_baslangici
            hucre = "".join(self._parcalar[baslangic:]).strip()
            del self._parcalar[baslangic:]
            self._hucreler.append(hucre)
            return
        if tag == "tr" and self._hucreler is not None:
            self._satiri_yaz()
            return
        if tag == "table":
            self._tablo_basligi_yazildi = False
            self._tablo_satiri_yazildi = False
        if tag in _BLOKLAR:
            self._blok_ac()

    def handle_data(self, data: str) -> None:
        if self._atlanan:
            return
        if self._pre_derinlik:
            self._pre_metin.append(data)
            return
        metin = re.sub(r"[ \t]*\n[ \t]*", " ", data)
        if not metin.strip():
            if metin and self._parcalar and not self._parcalar[-1].endswith((" ", "\n")):
                self._yaz(" ")
            return
        self._yaz(metin)

    # -- iç mantık ------------------------------------------------------
    def _dil_etiketini_dusur(self) -> None:
        """Kod bloğunun hemen üstündeki tek kelimelik dil etiketini at.

        Sağlayıcı arayüzü bu etiketi ayrı bir kutuda çiziyor; metne karışınca
        kod içeriğinin ilk satırı oluyordu.
        """
        onceki = "".join(self._parcalar).rstrip()
        if not onceki:
            return
        son_satir = onceki.rsplit("\n", 1)[-1].strip().rstrip(".:")
        if son_satir.lower() in _DIL_ETIKETLERI:
            kalan = onceki[: len(onceki) - len(onceki.rsplit("\n", 1)[-1])]
            if not self._pre_dili:
                self._pre_dili = son_satir.lower() if son_satir.lower() != "plaintext" else ""
            self._parcalar = [kalan]

    def _satiri_yaz(self) -> None:
        hucreler = self._hucreler or []
        self._hucreler = None
        if not hucreler:
            return
        if self._tablo_basligi_yazildi or self._tablo_satiri_yazildi:
            self._yaz("\n")
        else:
            self._blok_ac()
        self._yaz("| " + " | ".join(hucreler) + " |")
        if self._basliktaydi and not self._tablo_basligi_yazildi:
            self._yaz("\n| " + " | ".join("---" for _ in hucreler) + " |")
            self._tablo_basligi_yazildi = True
        self._tablo_satiri_yazildi = True
        self._basliktaydi = False

    def sonuc(self) -> str:
        # Kapanmamış satır içi etiketler burada kapatılır; yarım HTML'de
        # "yarım **kalın" gibi asılı işaretler kalmasın.
        for isaret in reversed(self._acik_satirici):
            self._yaz(isaret)
        self._acik_satirici.clear()
        metin = "".join(self._parcalar)
        metin = _UC_VE_FAZLA_BOS_SATIR.sub("\n\n", metin)
        satirlar = [satir.rstrip() for satir in metin.split("\n")]
        return "\n".join(satirlar).strip()


def _dil_adi(attrs: list[tuple[str, str | None]]) -> str:
    """`class="language-python"` gibi bir sınıftan dil adını çıkar."""
    sinif = dict(attrs).get("class") or ""
    eslesme = _DIL_SINIFI.search(sinif)
    return eslesme.group(1).lower() if eslesme else ""


def html_to_markdown(html: str) -> str:
    """Sağlayıcı sayfasındaki cevabı Markdown'a çevir.

    Ayrıştırma hiç yapılamazsa etiketler sökülmüş düz metin döner: biçim kaybı,
    içerik kaybından iyidir.
    """
    if not html or not html.strip():
        return ""
    donusturucu = _MarkdownDonusturucu()
    try:
        donusturucu.feed(html)
        donusturucu.close()
    except Exception:  # pragma: no cover - ayrıştırıcı hatası beklenmez
        return _UC_VE_FAZLA_BOS_SATIR.sub("\n\n", unescape(re.sub(r"<[^>]+>", "", html))).strip()
    return donusturucu.sonuc()

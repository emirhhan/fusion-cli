"""Seslendirilecek metnin hazırlanması.

Fusion'ın cevabı markdown, dosya yolu, kod bloğu ve sayı doludur. Ham hâliyle
sentezleyiciye verilirse hangi model kullanılırsa kullanılsın kulağa berbat
gelir: yıldızlar, ters tırnaklar ve eğik çizgiler tek tek telaffuz edilir.

Bu katman modelden BAĞIMSIZDIR. Yarın daha iyi bir ses modeline geçilse de
aynen çalışmaya devam eder; kazancın büyük kısmı burada üretilir.
"""

from __future__ import annotations

import re

#: Seslendirilecek metnin üst sınırı. Uzun cevabın tamamını okumak kullanıcıyı
#: dakikalarca bekletir; kesildiği AÇIKÇA söylenir, sessizce yarıda kesilmez.
MAX_CHARS = 4_000

#: Birim kısaltmaları → Türkçe okunuşu. Sıra önemlidir: uzun ek önce eşleşmeli
#: ("ms" ile "s" karışmasın).
_UNITS: tuple[tuple[str, str], ...] = (
    ("GB", "gigabayt"),
    ("MB", "megabayt"),
    ("KB", "kilobayt"),
    ("ms", "milisaniye"),
    ("kHz", "kilohertz"),
    ("Hz", "hertz"),
    ("px", "piksel"),
    ("s", "saniye"),
)

#: Sık geçen uzantılar → okunuşu. Harf harf okumak ("te es iks") anlaşılır ama
#: yorucu; yaygın olanlar kelimeye çevrilir.
_EXTENSIONS: dict[str, str] = {
    "tsx": "te es iks",
    "ts": "te es",
    "jsx": "ce es iks",
    "js": "ce es",
    "py": "pay",
    "rs": "rust",
    "md": "markdown",
    "json": "ceyson",
    "css": "se es es",
    "html": "eyç te em el",
    "yml": "yaml",
    "yaml": "yaml",
    "toml": "toml",
    "png": "pe en ge",
    "svg": "es ve ge",
}

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_EMPHASIS = re.compile(r"(\*\*|__|\*|_)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
#: Dosya yolu. En az bir HARF içermesi şart: aksi hâlde "169/169" gibi bir
#: kesir yol sanılır ve yalnız son parçası okunurdu (ölçüldü).
_PATH = re.compile(r"(?:[\w.-]+/)+[\w.-]*[A-Za-zÇĞİÖŞÜçğıöşü][\w.-]*")
_FRACTION = re.compile(r"\b(\d+)\s*/\s*(\d+)\b")
_PERCENT = re.compile(r"%\s*(\d+(?:[.,]\d+)?)")
#: Ondalık sayı. Sağ sınırda `\b` KULLANILAMAZ: "2.4s" gibi birim ekiyle
#: bitişik yazımda sınır oluşmaz ve dönüşüm hiç çalışmazdı.
_DECIMAL = re.compile(r"\b(\d+)[.,](\d+)(?![\d.,])")
_SENTENCE = re.compile(r"[^.!?…]+[.!?…]*")


def _strip_markdown(text: str) -> str:
    """Markdown işaretlerini kaldır; kod bloğunu tek bir ifadeye indir."""
    text = _CODE_BLOCK.sub(" kod bloğu. ", text)
    text = _LINK.sub(r"\1", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _HEADING.sub("", text)
    return _EMPHASIS.sub("", text)


def _speak_path(match: re.Match[str]) -> str:
    """Dosya yolunu okunabilir hâle getir: yalnız son parça ve uzantısı okunur.

    Tam yolu okumak ("app bölü src bölü screens bölü…") hem uzun hem yorucu;
    kullanıcı için anlamlı olan dosyanın adıdır.
    """
    son = match.group(0).rstrip("/").split("/")[-1]
    if "." not in son:
        return son
    govde, _, uzanti = son.rpartition(".")
    okunus = _EXTENSIONS.get(uzanti.casefold())
    return f"{govde} nokta {okunus}" if okunus else f"{govde} nokta {uzanti}"


def _speak_units(text: str) -> str:
    for kisa, uzun in _UNITS:
        text = re.sub(rf"(\d)\s*{re.escape(kisa)}\b", rf"\1 {uzun}", text)
    return text


def prepare_speech(text: str) -> str:
    """Metni seslendirilebilir hâle getir.

    Boş ya da yalnız boşluktan ibaret metin boş döner: sentezleyiciye anlamsız
    girdi göndermek yerine hiç konuşmamak doğrudur.
    """
    if not text or not text.strip():
        return ""
    hazir = _strip_markdown(text)
    # Kesir yoldan ÖNCE çevrilir: "169/169" bir dosya yolu değildir.
    hazir = _FRACTION.sub(r"\1 bölü \2", hazir)
    hazir = _PATH.sub(_speak_path, hazir)
    hazir = _PERCENT.sub(r"yüzde \1", hazir)
    hazir = _DECIMAL.sub(r"\1 virgül \2", hazir)
    hazir = _speak_units(hazir)
    # Okunmayan işaretler sessizliğe çevrilir; tek tek telaffuz edilmemeli.
    hazir = re.sub(r"[|>*_~^{}\[\]<]+", " ", hazir)
    hazir = re.sub(r"[ \t]+", " ", hazir)
    hazir = re.sub(r"\n{2,}", ". ", hazir).replace("\n", " ")
    hazir = re.sub(r"\s+([.,!?…])", r"\1", hazir).strip()
    if len(hazir) > MAX_CHARS:
        kes = hazir.rfind(" ", 0, MAX_CHARS)
        hazir = hazir[: kes if kes > 0 else MAX_CHARS].rstrip()
        hazir += " … Cevabın tamamı uzun olduğu için kısaltıldı, ekranda hepsi var."
    return hazir


def split_sentences(text: str) -> list[str]:
    """Metni cümlelere böl.

    Sentezleyiciye cümle cümle vermek iki işe yarar: cümle aralarına doğal
    duraklama girer ve kullanıcı konuşmayı durdurduğunda tepki anında olur.
    """
    return [parca.strip() for parca in _SENTENCE.findall(text) if parca.strip()]

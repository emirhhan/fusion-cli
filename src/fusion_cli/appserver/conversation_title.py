"""Sohbet başlığı — ilk kullanıcı mesajından kısa ve anlamlı bir ad.

Claude, ilk mesajdan sonra sohbete kısa bir başlık verir. Fusion'da başlık
mesajın ilk birkaç kelimesiydi: "merhaba bana bir oyun" gibi, selamlama ve
dolgu kelimeleri başlığın yarısını yiyordu (bulgu H9).

Model ÇAĞRILMAZ: web sağlayıcıda bir tur 10 saniyeyi aşıyor ve kotalı; bir
başlık için ek tur harcamak kabul edilemez. Bu yüzden saf ve deterministik bir
sezgisel kullanılır: kod bloğu ve bağlantı sadeleştirilir, ilk ANLAMLI cümle
alınır, baştaki selamlama/dolgu ve sondaki nezaket kalıbı atılır, sınırda
kelime ortasından değil kelime arasından kesilir, baş harf Türkçe kurala göre
büyütülür.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

__all__ = ["TITLE_MAX_CHARS", "conversation_title"]

#: Başlığın en fazla uzunluğu.
#
# Kenar çubuğu dar pencerede ~35-40 karakter gösterir, fazlası üç noktayla
# kısalır; Claude'un verdiği başlıklar da çoğunlukla 3-6 kelime (≈50 karakter
# altı) kalır. 50, kısalsa bile tanınacak kadar bilgi taşır.
TITLE_MAX_CHARS = 50

#: Cümle başından atılan selamlama ve dolgu kalıpları (Türkçe katlanmış).
#
# Çok kelimeli kalıplar ayrı tutulur: "iyi" tek başına anlamlıdır ("iyi bir
# README yaz"), yalnız "iyi akşamlar" selamlamadır.
_LEADING_FILLERS: tuple[tuple[str, ...], ...] = tuple(
    tuple(phrase.split())
    for phrase in (
        "iyi akşamlar",
        "iyi günler",
        "iyi geceler",
        "iyi çalışmalar",
        "kolay gelsin",
        "rica etsem",
        "bir de",
        "merhaba",
        "merhabalar",
        "mrb",
        "selam",
        "selamlar",
        "slm",
        "sa",
        "günaydın",
        "hey",
        "hi",
        "hello",
        "naber",
        "nasılsın",
        "hocam",
        "dostum",
        "abi",
        "kanka",
        "fusion",
        "lütfen",
        "acaba",
        "şimdi",
        "tamam",
        "tamamdır",
        "evet",
        "peki",
        "ok",
        "okey",
        "ya",
        "yani",
        "bana",
        "bir",
        "şu",
        "şunu",
    )
)

#: Cümle sonundan atılan nezaket kalıpları.
_TRAILING_FILLERS: tuple[tuple[str, ...], ...] = tuple(
    tuple(phrase.split())
    for phrase in (
        "lütfen",
        "rica ederim",
        "rica ediyorum",
        "teşekkürler",
        "teşekkür ederim",
        "sağ ol",
        "saol",
        "please",
    )
)

#: Kesilen başlığın sonunda asılı kalmaması gereken bağlaçlar.
_DANGLING_WORDS = frozenset({"ve", "veya", "ile", "ya", "da", "de", "için", "ama", "ki"})

#: Kelime kenarından atılan noktalama. Nokta yalnız sonda atılır; `#`, `@`,
#: `/` ve kelime içi noktalama (`config.py`, `e-posta`) korunur.
_EDGE_CHARS = "\"'«»“”‘’`()[]{}<>,;:!?…*~"

_CODE_BLOCK = re.compile(r"```.*?(?:```|$)", re.DOTALL)
_URL = re.compile(r"https?://\S+")
#: Cümle sınırı: noktalama + boşluk ya da satır sonu. `config.py` bölünmez.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…])\s+|\n+")


def conversation_title(message: str) -> str:
    """İlk kullanıcı mesajından başlık üret; anlamlı hiçbir şey yoksa boş döner."""
    sentences = [_words(sentence) for sentence in _SENTENCE_BREAK.split(_simplify(message))]
    sentences = [words for words in sentences if words]
    if not sentences:
        return ""
    meaningful = next(
        (stripped for words in sentences if (stripped := _strip_fillers(words))),
        # Yalnız selam yazılmışsa ("merhaba!") boş başlık yerine selamın kendisi.
        sentences[0],
    )
    return _capitalize(_fit(meaningful))


def _simplify(message: str) -> str:
    """Kod bloğunu at, bağlantıyı alan adına indir."""
    without_code = _CODE_BLOCK.sub("\n", message)
    return _URL.sub(lambda match: urlparse(match.group()).netloc or match.group(), without_code)


def _words(sentence: str) -> list[str]:
    stripped = (word.strip(_EDGE_CHARS) for word in sentence.split())
    return [word.rstrip(".") or word for word in stripped if word.strip(".")]


def _fold(word: str) -> str:
    """Türkçe büyük/küçük harf katlama: `İ`→`i`, `I`→`ı`."""
    return word.replace("İ", "i").replace("I", "ı").lower()


def _strip_fillers(words: list[str]) -> list[str]:
    start, end = 0, len(words)
    while (length := _matched_phrase(words, start, _LEADING_FILLERS)) > 0:
        start += length
    while end > start and (length := _matched_suffix(words[start:end])) > 0:
        end -= length
    return words[start:end]


def _matched_phrase(words: list[str], index: int, phrases: tuple[tuple[str, ...], ...]) -> int:
    folded = [_fold(word) for word in words[index : index + 3]]
    for phrase in phrases:
        if tuple(folded[: len(phrase)]) == phrase:
            return len(phrase)
    return 0


def _matched_suffix(words: list[str]) -> int:
    folded = tuple(_fold(word) for word in words[-3:])
    for phrase in _TRAILING_FILLERS:
        if folded[-len(phrase) :] == phrase:
            return len(phrase)
    return 0


def _fit(words: list[str]) -> str:
    """Sınırı aşmadan kelime arasından kes; asılı bağlacı at."""
    picked: list[str] = []
    for word in words:
        if len(" ".join([*picked, word])) > TITLE_MAX_CHARS:
            break
        picked.append(word)
    if not picked:
        # Tek kelime sınırı tek başına aşıyor: boş başlık yerine sert kesim.
        return words[0][:TITLE_MAX_CHARS]
    if len(picked) < len(words):
        while len(picked) > 1 and _fold(picked[-1]) in _DANGLING_WORDS:
            picked.pop()
    return " ".join(picked)


def _capitalize(title: str) -> str:
    if not title:
        return title
    first = {"i": "İ", "ı": "I"}.get(title[0], title[0].upper())
    return first + title[1:]

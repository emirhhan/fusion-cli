"""Yetenek aramasında kısa kelimeyi substring saymayan tek normalizasyon."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .capabilities import Capability


#: Hemen her açıklamada geçen sözcükler: skoru ayırt edici olmaktan çıkarır. Normalleştirilmiş
#: (küçük harf, diakritiksiz) biçimde tutulur.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "to", "for", "of", "and", "or", "in", "on", "with", "is", "are", "be",
        "my", "me", "it", "this", "that", "from", "by", "as", "at", "use", "using", "create",
        "build", "make", "code", "new", "i", "you", "can", "will", "when", "how",
        "ve", "ile", "bir", "bu", "icin", "de", "da", "mi", "mu", "ya", "yap", "olustur", "kur",
        "bana", "benim", "gibi", "daha", "cok", "en",
    }
)  # fmt: skip


def _query_terms(query: str) -> list[str]:
    """Sorgu terimleri: durak sözcükler ve tekrarlar atılır (hepsi durak ise hepsi korunur)."""
    terms = _search_terms(query)
    meaningful = [term for term in dict.fromkeys(terms) if term not in _STOPWORDS]
    return meaningful or list(dict.fromkeys(terms))


def search(items: tuple[Capability, ...], query: str, limit: int = 6) -> tuple[Capability, ...]:
    """Ad ve açıklama üzerinde kelime örtüşmesine göre ara.

    Basit ve öngörülebilir: hiç eşleşmeyenler elenir, en çok örtüşen öne gelir.
    Boş sorgu ilk `limit` girdiyi döndürür.
    """
    terms = _query_terms(query)
    if not terms:
        return items[:limit]
    return tuple(item for item, _ in search_scored(items, query, limit=limit))


def search_scored(
    items: tuple[Capability, ...], query: str, limit: int = 6
) -> tuple[tuple[Capability, int], ...]:
    """`search` ile aynı sıralama, ama eşleşme SKORUYLA birlikte.

    Skor, otomatik enjeksiyon kararı için gereklidir: tek kelimelik zayıf bir
    örtüşme aramada gösterilebilir ama sistem promptuna 2.500 karakter uzmanlık
    metni koymayı haklı çıkarmaz.
    """
    terms = _query_terms(query)
    if not terms:
        return tuple((item, 0) for item in items[:limit])
    scored = [(item, _score(item, terms)) for item in items]
    matching = [(item, score) for item, score in scored if score > 0]
    matching.sort(key=lambda pair: pair[1], reverse=True)
    return tuple(matching[:limit])


#: Kısa in/er/ve ve beş harfli ortak köklerde agresif ek düşürmeyi önler.
_MIN_STEM_CHARS = 6


def _search_terms(text: str) -> list[str]:
    """Diakritik ve sınırlı uzun ekleri eşleştir; kısa substring eşleşmesi yok."""
    normalized = unicodedata.normalize("NFKD", text.casefold().replace("ı", "i"))
    plain = "".join(char for char in normalized if not unicodedata.combining(char))
    words = re.findall(r"[a-z0-9]+", plain)
    suffixes = ("lari", "leri", "lar", "ler", "mak", "mek", "lu", "li")
    return [
        next(
            (
                word[: -len(suffix)]
                for suffix in suffixes
                if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM_CHARS
            ),
            word,
        )
        for word in words
    ]


def _score(item: Capability, terms: list[str]) -> int:
    """Kaç arama terimi ad/açıklamada KELİME olarak geçiyor.

    Alt-dize değil kelime eşleşmesi: Türkçe görev metnindeki kısa kelimeler
    ("ve", "in", "er") İngilizce açıklamaların İÇİNDE eşleşip ("de-ve-lopment",
    "serv-er") tamamen alakasız skill'leri öne çıkarıyordu.
    """
    return _overlap(f"{item.name} {item.description}", terms)


def relevance_score(name: str, description: str, query: str) -> int:
    """Araç yüzeyi ve yetenek araması için aynı sözcük örtüşmesini kullan."""
    return _overlap(f"{name} {description}", _query_terms(query))


def _overlap(text: str, terms: list[str]) -> int:
    haystack = set(_search_terms(text))
    return sum(1 for term in terms if term in haystack)

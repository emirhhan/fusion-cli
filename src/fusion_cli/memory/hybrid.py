"""Hibrit geri çağırma — lexical skoru embedding sırasıyla birleştirir.

Salt embedding (kosinüs) Türkçe metin + İngilizce/kod tanımlayıcıları karışımında
zayıf kalır: "multi_edit" ya da "run_shell" gibi birebir terimler anlamsal komşuda
kaybolur. Buraya bir lexical katman (aday havuzu üzerinde BM25) eklenir ve iki sıra
**Reciprocal Rank Fusion** ile birleştirilir.

RRF bilinçli tercih: skorları normalize etmeye gerek yok (mesafe ile BM25 farklı
ölçekte), yalnızca sıralamalar birleşir; ayrıca reranker MODELİ yok — ayak izi
şişmesin, yerel ve ucuz kalsın.

Modül saftır: ChromaDB tanımaz, yan etkisi yoktur, doğrudan test edilir.
"""

from __future__ import annotations

import math
import re

#: RRF yumuşatma sabiti. Büyük k, tek bir sıralamanın baskınlığını azaltır (standart 60).
RRF_K = 60
#: Aday havuzu, istenen limitin kaç katı geniş çekilir — lexical eşleşme elenmeden yakalansın.
CANDIDATE_MULTIPLIER = 3

# BM25 parametreleri (literatürdeki yaygın varsayılanlar).
_BM25_K1 = 1.5
_BM25_B = 0.75
#: Bir tokenın anlamlı sayılması için asgari uzunluk.
_MIN_TOKEN_LENGTH = 2


def tokenize(text: str) -> list[str]:
    """Metni küçük harfli, alfasayısal token listesine ayırır (Türkçe harfler dahil)."""

    words = re.split(r"[^0-9a-zçğıöşü]+", text.lower())
    return [word for word in words if len(word) >= _MIN_TOKEN_LENGTH]


def bm25_scores(query: str, documents: list[str]) -> list[float]:
    """Sorgu için her belgenin BM25 skoru. Corpus istatistiği aday havuzundan gelir.

    Boş sorgu ya da boş havuzda hepsi 0.0 döner (lexical katkı yok, embedding'e bırakılır).
    """

    query_terms = set(tokenize(query))
    if not query_terms or not documents:
        return [0.0] * len(documents)

    tokenized = [tokenize(document) for document in documents]
    lengths = [len(tokens) for tokens in tokenized]
    total_docs = len(documents)
    avg_length = sum(lengths) / total_docs if total_docs else 0.0

    document_frequency = _document_frequency(query_terms, tokenized)
    return [
        _bm25_document_score(
            query_terms, tokens, lengths[index], avg_length, document_frequency, total_docs
        )
        for index, tokens in enumerate(tokenized)
    ]


def reciprocal_rank_fusion(
    distances: list[float], lexical_scores: list[float], *, k: int = RRF_K
) -> list[float]:
    """İki sıralamayı RRF ile birleştir: her aday için birleşik skor (yüksek = iyi).

    Embedding sırası mesafeye göre artan (yakın önce), lexical sıra skora göre azalan
    (yüksek önce) kurulur. Uzunluklar eşit değilse (savunma amaçlı) 0.0 listesi döner.
    """

    if len(distances) != len(lexical_scores) or not distances:
        return [0.0] * len(distances)

    embedding_rank = _ranks(distances, ascending=True)
    lexical_rank = _ranks(lexical_scores, ascending=False)
    return [
        1.0 / (k + embedding_rank[index]) + 1.0 / (k + lexical_rank[index])
        for index in range(len(distances))
    ]


def _ranks(values: list[float], *, ascending: bool) -> list[int]:
    """Her indeks için 0-tabanlı sıra (eşit değerler eşit sıra alır).

    Eşitlere aynı sıra vermek kritiktir: lexical sinyal yoksa (tüm skorlar 0) bu terim
    sabitlenir ve birleşik sıralama tümüyle embedding'e iner — gürültü katılmaz.
    """

    ranks: list[int] = []
    for value in values:
        if ascending:
            ranks.append(sum(1 for other in values if other < value))
        else:
            ranks.append(sum(1 for other in values if other > value))
    return ranks


def _document_frequency(query_terms: set[str], tokenized: list[list[str]]) -> dict[str, int]:
    frequency: dict[str, int] = {}
    for term in query_terms:
        frequency[term] = sum(1 for tokens in tokenized if term in tokens)
    return frequency


def _bm25_document_score(
    query_terms: set[str],
    tokens: list[str],
    length: int,
    avg_length: float,
    document_frequency: dict[str, int],
    total_docs: int,
) -> float:
    score = 0.0
    for term in query_terms:
        term_frequency = tokens.count(term)
        if term_frequency == 0:
            continue
        idf = _idf(document_frequency[term], total_docs)
        denominator = term_frequency + _BM25_K1 * (
            1 - _BM25_B + _BM25_B * (length / avg_length if avg_length else 0.0)
        )
        score += idf * (term_frequency * (_BM25_K1 + 1)) / denominator
    return score


def _idf(document_frequency: int, total_docs: int) -> float:
    """BM25 ters belge sıklığı; her zaman pozitif kalan (log1p'li) biçim."""

    return math.log(1 + (total_docs - document_frequency + 0.5) / (document_frequency + 0.5))

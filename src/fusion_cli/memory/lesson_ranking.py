"""Ders geri çağırma sıralaması — saf seçim.

Anlamsal sorgudan dönen adayları iki koruma ile eler ve sıralar:

- **Alaka eşiği** — kosinüs mesafesi eşiği aşan ders alakasız sayılır, enjekte edilmez.
- **Güven eşiği** — güveni düşük (zamanla zehirlendiği görülen) ders enjekte edilmez.

Kalanlar önce türe (hata öne: bir şeyi yanlış yapmamak kritiktir), sonra güvene, en
son yakınlığa göre sıralanır. Saftır; ChromaDB tanımaz, doğrudan test edilir.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.memory import Lesson, LessonKind
from .lesson_scoring import is_injectable

#: Kosinüs mesafesi eşiği: 0 aynı, 1 ilgisiz. Bunun ötesindeki ders alakasız sayılır.
MAX_RELEVANCE_DISTANCE = 0.66


@dataclass(frozen=True, slots=True)
class Candidate:
    """Sorgudan dönen tek aday: ders, embedding uzaklığı ve (varsa) lexical/füzyon skoru.

    `lexical` ve `fused` varsayılan 0.0'dır: salt-embedding yolunda (lexical katman
    devrede değilken) sıralama Faz 1'deki gibi uzaklığa iner. Hibrit yolda bunlar
    doldurulur ve füzyon skoru sıralamayı belirler.
    """

    lesson: Lesson
    distance: float
    #: Aday havuzu üzerinde hesaplanan BM25 lexical skoru (yüksek = iyi).
    lexical: float = 0.0
    #: Embedding ve lexical sıralarının RRF birleşimi (yüksek = iyi).
    fused: float = 0.0


def select_lessons(
    candidates: tuple[Candidate, ...],
    *,
    limit: int,
    max_distance: float = MAX_RELEVANCE_DISTANCE,
    scope: str | None = None,
) -> tuple[Lesson, ...]:
    """Alaka, güven ve kapsam eşiğini geçen dersleri sıralayıp en iyi `limit` tanesini döndürür.

    Bir aday, embedding'e göre yeterince yakınsa (`distance <= max_distance`) YA DA
    lexical bir eşleşmesi varsa (`lexical > 0`) alakalı sayılır — lexical katman,
    embedding'in ıskaladığı birebir terim eşleşmesini kurtarır.
    """

    relevant = [
        candidate
        for candidate in candidates
        if _is_relevant(candidate, max_distance)
        and is_injectable(candidate.lesson)
        and _scope_matches(candidate.lesson.scope, scope)
    ]
    relevant.sort(key=_rank_key)
    return tuple(candidate.lesson for candidate in relevant[:limit])


def _is_relevant(candidate: Candidate, max_distance: float) -> bool:
    return candidate.distance <= max_distance or candidate.lexical > 0.0


def _scope_matches(lesson_scope: str, wanted: str | None) -> bool:
    """Kapsamı boş (genel) ders her göreve uyar; belirli kapsam yalnızca eşleşince uyar."""
    if wanted is None or not lesson_scope:
        return True
    return lesson_scope == wanted


def _rank_key(candidate: Candidate) -> tuple[int, float, float, float]:
    lesson = candidate.lesson
    kind_rank = 0 if lesson.kind is LessonKind.MISTAKE else 1
    # Hata öne; sonra güven; sonra füzyon skoru (yüksekten); en son uzaklık (yakından).
    # Füzyon ve lexical devrede değilken (0.0) sıralama Faz 1'deki uzaklığa iner.
    return (kind_rank, -lesson.confidence, -candidate.fused, candidate.distance)

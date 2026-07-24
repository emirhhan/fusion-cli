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
    """Sorgudan dönen tek aday: ders + göreve uzaklığı."""

    lesson: Lesson
    distance: float


def select_lessons(
    candidates: tuple[Candidate, ...],
    *,
    limit: int,
    max_distance: float = MAX_RELEVANCE_DISTANCE,
) -> tuple[Lesson, ...]:
    """Alaka ve güven eşiğini geçen dersleri sıralayıp en iyi `limit` tanesini döndürür."""

    relevant = [
        candidate
        for candidate in candidates
        if candidate.distance <= max_distance and is_injectable(candidate.lesson)
    ]
    relevant.sort(key=_rank_key)
    return tuple(candidate.lesson for candidate in relevant[:limit])


def _rank_key(candidate: Candidate) -> tuple[int, float, float]:
    lesson = candidate.lesson
    kind_rank = 0 if lesson.kind is LessonKind.MISTAKE else 1
    # Güven yüksekten düşüğe: negatifleyerek artan sıralamada öne al.
    return (kind_rank, -lesson.confidence, candidate.distance)

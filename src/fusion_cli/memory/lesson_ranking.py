"""Ders geri çağırma sıralaması — saf seçim.

Anlamsal sorgudan dönen adayları iki koruma ile eler ve sıralar:

- **Alaka eşiği** — kosinüs mesafesi eşiği aşan ders alakasız sayılır, enjekte edilmez.
- **Güven eşiği** — güveni düşük (zamanla zehirlendiği görülen) ders enjekte edilmez.

Kalanlar önce türe (hata öne: bir şeyi yanlış yapmamak kritiktir), sonra güvene, en
son yakınlığa göre sıralanır. Saftır; ChromaDB tanımaz, doğrudan test edilir.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.memory import Lesson, LessonKind, LessonRecallPolicy
from .lesson_scoring import is_injectable

#: Kosinüs mesafesi eşiği: 0 aynı, 1 ilgisiz. Bunun ötesindeki ders alakasız sayılır.
MAX_RELEVANCE_DISTANCE = 0.66

#: Alaka BANDI genişliği. Aynı banda düşen dersler "benzer ölçüde alakalı"dır.
#:
#: Alakayı ham sayı olarak birincil ölçüt yapmak ölçülerek yanlış bulundu: uzun ve
#: genel derslerin zayıf lexical eşleşmesi kıl payı öne geçiyor ve Godot görevine
#: tek bir Godot dersi gelmiyordu. Band, alakanın KABACA karar vermesini sağlar;
#: aynı bandın içinde güven seçer.
RELEVANCE_BAND = 0.1


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
    #: Dersin güveninin en son kaç saniye önce güncellendiği (eşik altı yeniden deneme için).
    idle_s: float = 0.0


def select_lessons(
    candidates: tuple[Candidate, ...],
    *,
    limit: int,
    max_distance: float = MAX_RELEVANCE_DISTANCE,
    scope: str | None = None,
    policy: LessonRecallPolicy | None = None,
) -> tuple[Lesson, ...]:
    """Alaka, güven ve kapsam eşiğini geçen dersleri sıralayıp en iyi `limit` tanesini döndürür.

    Bir aday, embedding'e göre yeterince yakınsa (`distance <= max_distance`) YA DA
    lexical bir eşleşmesi varsa (`lexical > 0`) alakalı sayılır — lexical katman,
    embedding'in ıskaladığı birebir terim eşleşmesini kurtarır.
    """

    if policy is not None:
        candidates = _apply_policy(
            tuple(
                item
                for item in candidates
                if _scope_matches(item.lesson.scope, scope)
                and is_injectable(item.lesson, idle_s=item.idle_s)
            ),
            policy,
        )
    relevant = [
        candidate
        for candidate in candidates
        if _is_relevant(candidate, max_distance)
        and is_injectable(candidate.lesson, idle_s=candidate.idle_s)
        and _scope_matches(candidate.lesson.scope, scope)
    ]
    relevant.sort(key=_rank_key)
    return tuple(candidate.lesson for candidate in relevant[:limit])


def _relevance_band(candidate: Candidate) -> int:
    """Adayın alaka bandı: küçük sayı daha yakın. Kıl payı farklar aynı banda düşer.

    Küçük bir tolerans eklenir: `0.30 / 0.1` kayan noktada 2.9999… çıkar ve band
    bir aşağı kayardı; 0.30 ile 0.34 farklı bandlara düşerdi.
    """
    return int(candidate.distance / RELEVANCE_BAND + 1e-9)


def _is_relevant(candidate: Candidate, max_distance: float) -> bool:
    return candidate.distance <= max_distance or candidate.lexical > 0.0


def _scope_matches(lesson_scope: str, wanted: str | None) -> bool:
    """Kapsamı boş (genel) ders her göreve uyar; belirli kapsam yalnızca eşleşince uyar."""
    if wanted is None or not lesson_scope:
        return True
    return lesson_scope == wanted


def _rank_key(candidate: Candidate) -> tuple[int, int, float, float, float]:
    lesson = candidate.lesson
    kind_rank = 0 if lesson.kind is LessonKind.MISTAKE else 1
    # Hata öne (bir şeyi yanlış yapmamak kritiktir); sonra ALAKA BANDI; sonra
    # güven; en son ince alaka farkları.
    #
    # İki uç da ölçülerek elendi. Güven alakadan önce geldiğinde: bellek 380
    # derse çıkınca "stripe ile iade yap" sorgusu, konuyla ilgisiz ama güveni
    # 1.00 olan dosya-yazma derslerini getiriyordu. Ham alaka güvenden önce
    # geldiğinde: uzun ve genel derslerin zayıf lexical eşleşmesi kıl payı öne
    # geçti ve bir Godot görevine tek bir Godot dersi gelmedi.
    #
    # Doğrusu ikisinin arası: alaka KABACA (band) karar verir, aynı bandın
    # içinde güven seçer.
    return (
        kind_rank,
        _relevance_band(candidate),
        -lesson.confidence,
        -candidate.fused,
        candidate.distance,
    )


def _apply_policy(
    candidates: tuple[Candidate, ...],
    policy: LessonRecallPolicy,
) -> tuple[Candidate, ...]:
    """Bağlam dışı kaydı eleyip açık, doğrulanmış haleflerin eskilerini bastır."""
    eligible = tuple(item for item in candidates if _policy_matches(item.lesson, policy))
    if not policy.conflict_quarantine:
        return eligible
    current = tuple(
        item
        for item in eligible
        if not any(_supersedes(other.lesson, item.lesson) for other in eligible)
    )
    return tuple(
        item
        for item in current
        if not any(_conflicts(item.lesson, other.lesson) for other in current)
    )


def _policy_matches(lesson: Lesson, policy: LessonRecallPolicy) -> bool:
    return (
        not lesson.quarantined
        and (not policy.subject_key or lesson.subject_key == policy.subject_key)
        and (not policy.version or not lesson.version or lesson.version == policy.version)
        and (not policy.source_split or lesson.source_split == policy.source_split)
        and (
            not policy.applies_to
            or not lesson.applies_to
            or bool(set(lesson.applies_to).intersection(policy.applies_to))
        )
    )


def _supersedes(new: Lesson, old: Lesson) -> bool:
    return bool(
        new.id != old.id
        and old.id
        and old.id in new.supersedes
        and new.subject_key
        and new.subject_key == old.subject_key
        and new.verified_at
        and new.evidence_refs
        and (
            not new.applies_to
            or not old.applies_to
            or set(new.applies_to).intersection(old.applies_to)
        )
    )


def _conflicts(first: Lesson, second: Lesson) -> bool:
    """Açık konu kimliği tek bir iddiayı temsil eder; çözümsüz varyantlar bekler."""
    return bool(
        first.id != second.id
        and first.subject_key
        and first.subject_key == second.subject_key
        and first.source_split == second.source_split
        and first.text.strip().lower() != second.text.strip().lower()
        and (
            not first.applies_to
            or not second.applies_to
            or set(first.applies_to).intersection(second.applies_to)
        )
    )

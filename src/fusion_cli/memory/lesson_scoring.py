"""Ders güveni — öz-düzeltmenin saf çekirdeği.

`performance.py`'deki `Feedback.delta` desenini derslere uygular: bir ders enjekte
edildiği turun sonucuna göre ödüllenir ya da cezalanır. Başarısızlık kasıtlı olarak
daha sert biter — yerel olarak zehirlenmiş (yanlış) bir ders hızla eşiğin altına
düşüp enjekte edilmez olsun.

Saftır: `Lesson` alıp `dataclasses.replace` ile YENİ bir `Lesson` döndürür; girdi
mutasyona uğramaz. Doğrudan test edilir.
"""

from __future__ import annotations

from dataclasses import replace

from ..core.memory import Lesson

#: Başarılı turda güvene eklenen miktar.
LESSON_SUCCESS_DELTA = 0.10
#: Başarısız turda güvenden düşülen miktar (başarıdan sert).
LESSON_FAILURE_DELTA = 0.20
#: Bu güvenin altındaki ders artık enjekte edilmez.
LESSON_CONFIDENCE_FLOOR = 0.35


def reinforced(lesson: Lesson, *, success: bool) -> Lesson:
    """Dersin güvenini ve sayaçlarını tur sonucuna göre güncellenmiş kopyayla döndürür."""

    delta = LESSON_SUCCESS_DELTA if success else -LESSON_FAILURE_DELTA
    return replace(
        lesson,
        confidence=_clamp(lesson.confidence + delta),
        success_count=lesson.success_count + (1 if success else 0),
        failure_count=lesson.failure_count + (0 if success else 1),
    )


def is_injectable(lesson: Lesson) -> bool:
    """Güven eşiği: bu dersin sistem promptuna enjekte edilmesine izin var mı."""

    return lesson.confidence >= LESSON_CONFIDENCE_FLOOR


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

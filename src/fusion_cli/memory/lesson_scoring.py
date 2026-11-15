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
from ..core.repair_ledger import FailureOrigin

#: Başarılı turda güvene eklenen miktar.
LESSON_SUCCESS_DELTA = 0.10
#: Başarısız turda güvenden düşülen miktar (başarıdan sert).
LESSON_FAILURE_DELTA = 0.20
#: Bu güvenin altındaki ders artık enjekte edilmez.
LESSON_CONFIDENCE_FLOOR = 0.35
#: Eşik altındaki ders, güveni bu süre (sn) güncellenmeden durduysa YENİDEN denenir.
#:
#: Ölçüldü (29 Ekim): `reinforce` yalnız enjekte edilen derslere çağrıldığı için eşiğin
#: altına inen ders bir daha asla ödüllenmiyordu ("ölü"). Zayıf bir modelin iki başarısız
#: turu (0.6 → 0.2) iyi bir dersi kalıcı kapatabiliyordu; 7 günlük bekleme sonrası ders
#: bir tur daha şans alır, başarırsa güveni yükselir, başarısızsa güveni yeniden düşer ve
#: bekleme süresi baştan başlar (`reinforce` zaman damgasını yeniler).
LESSON_REVIVE_AFTER_S = 7 * 24 * 3600.0


VERIFIED_OUTCOME_REASON = "verified_outcome"


def reinforced(
    lesson: Lesson,
    *,
    success: bool,
    external_turn: bool = False,
    feedback_reason: str | None = None,
    evidence_refs: tuple[str, ...] = (),
    used: bool | None = None,
    failure_origin: FailureOrigin = FailureOrigin.PRODUCT,
    verified_at: str = "",
) -> Lesson:
    """Dersin güvenini ve sayaçlarını tur sonucuna göre güncellenmiş kopyayla döndürür.

    `external_turn`: tur dış içerik (web/MCP/klonlanan site) okudu. Dış kaynaklı ve henüz
    doğrulanmamış ders böyle bir başarıyla GÜVEN KAZANMAZ (dış metin hem dersi hem
    "başarıyı" etkilemiş olabilir); dış içeriksiz başarılı tur dersi doğrular
    (`external=False`) ve normal artış uygulanır. Başarısızlık her durumda normal cezadır.
    """

    if failure_origin is not FailureOrigin.PRODUCT:
        return lesson
    has_attribution = feedback_reason is not None or bool(evidence_refs) or used is not None
    has_attribution = has_attribution or bool(verified_at)
    if has_attribution and (
        feedback_reason != VERIFIED_OUTCOME_REASON
        or used is not True
        or not evidence_refs
        or not all(reference.strip() for reference in evidence_refs)
        or (success and not verified_at)
    ):
        return lesson
    if lesson.external and success and external_turn:
        return lesson
    delta = LESSON_SUCCESS_DELTA if success else -LESSON_FAILURE_DELTA
    return replace(
        lesson,
        confidence=_clamp(lesson.confidence + delta),
        success_count=lesson.success_count + (1 if success else 0),
        failure_count=lesson.failure_count + (0 if success else 1),
        external=lesson.external and not success,
        verified_at=verified_at if success and feedback_reason is not None else lesson.verified_at,
        evidence_refs=tuple(dict.fromkeys((*lesson.evidence_refs, *evidence_refs))),
    )


def is_injectable(lesson: Lesson, *, idle_s: float = 0.0) -> bool:
    """Güven eşiği: bu dersin sistem promptuna enjekte edilmesine izin var mı.

    `idle_s`: dersin güveni en son kaç saniye önce güncellendi. Eşik altı ders bekleme
    süresini doldurduysa yeniden denenebilir (bkz. `LESSON_REVIVE_AFTER_S`).
    """

    return lesson.confidence >= LESSON_CONFIDENCE_FLOOR or idle_s >= LESSON_REVIVE_AFTER_S


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

"""Öğretmen cevabını ders belleğine (opsiyonel) yaz — çakışma kontrolüyle.

Faz 4, Görev 3, §6.3 kararı: öğretmen dersleri VARSAYILAN olarak
`ChromaLessonMemory`'ye de yazılır (model `recall_lessons` ile geri
çağırabilsin), ama bu `runtime.teacher_lesson_sync` ile açılıp kapatılabilir.
İKİ PARALEL DERS SİSTEMİ açılmaz: `.fusion/ogretmen.md` (insan-okunur günlük,
`teacher_notebook.py`) ve bu modül AYNI kaynaktan (öğretmenin cevabı) beslenir
ama farklı amaçlar taşır — biri denetim, biri geri-çağrılabilir bellek.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...core.events import TeacherAdviceOutcome
from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.execution_plan import VerificationCheck, VerificationCheckKind
from ...core.redaction import redact

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome

from ...core.memory import Lesson, LessonKind, LessonMemory, LessonRecallPolicy, LessonSource

#: Bir ders metninde olumsuzlama/yasaklama işareti. Kaba bir sezgi: iki ders
#: AYNI konudan bahsediyorsa (`recall` zaten bunu garanti eder — yeterince
#: benzer olmasalar geri gelmezler) ama yalnız BİRİNDE bu işaretlerden biri
#: varsa, muhtemelen TERS yönde talimat veriyorlardır. Kusursuz değil — yanlış
#: pozitif/negatif üretebilir — ama sessizce çelişen iki dersi aynı anda
#: belleğe koymaktan daha güvenlidir. Belirsizlikte YAZILIR: ders belleğini
#: agresif biçimde kısırlaştırmaz.
#
#: Alt dize eşlemesi `yapma` ⊂ `yapmak`, `etme` ⊂ `gözetme` gibi sözcüklerde yanlış tetikliyordu
#: ve uzun cevapların hemen hepsi "olumsuzlamalı" görünüyordu (A4-35): sözcük sınırı aranır.
_CATISMA_ISARETLERI = re.compile(
    r"(?<!\w)(?:değil|(?:yap|kullan|et)(?:ma|mayın|meyin)|asla|sakın|olmaz|yanlış)(?!\w)",
    re.IGNORECASE,
)

#: Ders metni olarak saklanacak öğretmen cevabının üst sınırı. Ders belleği kısa,
#: yordamsal dersler için tasarlanmıştır (bkz. `memory/lessons.py`); öğretmenin
#: tüm cevabını sınırsız saklamak onu uzun bir deneme metnine çevirir.
_LESSON_TEXT_LIMIT = 2_000


def sync_teacher_lesson(
    memory: LessonMemory, *, question: str, answer: str, metadata: Lesson | None = None
) -> tuple[bool, str]:
    """Öğretmen cevabını derse çevirip belleğe yaz.

    `(yazıldı_mı, atlama_gerekçesi)` döner — gerekçe yalnız `yazıldı_mı=False`
    iken doludur ve `.fusion/ogretmen.md` günlüğüne + kullanıcıya bildirime
    aktarılır (bkz. çağıran yer, `engine_tools._ask_teacher_tool`).
    """
    metin = answer.strip()[:_LESSON_TEXT_LIMIT]
    if not metin:
        return False, "öğretmen boş cevap verdi"
    policy = LessonRecallPolicy(source_split=metadata.source_split) if metadata else None
    candidates = (
        memory.recall(question, limit=3, policy=policy)
        if policy is not None
        else memory.recall(question, limit=3)
    )
    for aday in candidates:
        if _olasi_catisma(metin, aday.text):
            kesit = aday.text[:80] + ("…" if len(aday.text) > 80 else "")
            return False, f"bellekteki bir dersle çelişebilir: {kesit!r}"
    yazildi = memory.add(
        replace(metadata, text=metin)
        if metadata
        else Lesson(text=metin, kind=LessonKind.SUCCESS, task=question, source=LessonSource.TEACHER)
    )
    if not yazildi:
        return False, "aynı ders zaten kayıtlı"
    return True, ""


def _olasi_catisma(yeni: str, mevcut: str) -> bool:
    yeni_isaretli = _CATISMA_ISARETLERI.search(yeni) is not None
    mevcut_isaretli = _CATISMA_ISARETLERI.search(mevcut) is not None
    return yeni_isaretli != mevcut_isaretli


@dataclass(frozen=True, slots=True)
class AdviceBinding:
    """Danışma öncesi executor'un ölçtüğü tek başarısız kriter ve dosya sürümü."""

    criterion: CriterionEvidence
    before_digest: str


@dataclass(frozen=True, slots=True)
class PendingAdvice:
    """Henüz sonucu bilinmeyen tavsiye; ölçülmeyen prose bağı kurulmaz."""

    advice_id: str
    question: str
    answer: str
    binding: AdviceBinding | None = None


def bind_advice(deps: AgentDeps, criterion_id: str) -> AdviceBinding | None:
    """Model yalnız mevcut ölçümün kimliğini seçer; hedef/beklentiyi üretemez."""
    from .plan_checkpoint import _digest
    from .step_verification import evaluate_file_check

    verification = deps.lesson_state.verification if deps.lesson_state else None
    if not criterion_id or verification is None:
        return None
    candidates = [item for item in verification.evidence if item.criterion_id == criterion_id]
    if len(candidates) != 1:
        return None
    criterion = candidates[0]
    if (
        not criterion.applicable
        or criterion.status is not EvidenceStatus.FAILED
        or not criterion.check_target
        or criterion.kind
        not in (VerificationCheckKind.FILE_EXISTS, VerificationCheckKind.FILE_CONTAINS)
    ):
        return None
    check = VerificationCheck(
        criterion.criterion_id, criterion.kind, criterion.check_target, criterion.check_expected
    )
    measured = evaluate_file_check(check, deps.tool_context.root)
    if not measured.applicable or measured.status is not EvidenceStatus.FAILED:
        return None
    return AdviceBinding(criterion, _digest(deps.tool_context.root, criterion.check_target))


def pending_advice(
    deps: AgentDeps, question: str, answer: str, binding: AdviceBinding | None = None
) -> PendingAdvice:
    """Read/touched kümesi tavsiyenin kullanım kanıtı değildir."""
    return PendingAdvice(deps.trace_id_factory(), redact(question), redact(answer), binding)


def _criterion_key(item: CriterionEvidence) -> tuple[str, VerificationCheckKind, str, str, str]:
    """Aynı dosyadaki başka kriter veya beklenti aynı tavsiye bağı değildir."""
    return item.criterion_id, item.kind, item.check_target, item.check_expected, item.step_id


def _advice_refs(advice: PendingAdvice, deps: AgentDeps) -> tuple[str, ...]:
    """Aynı hedef/beklenti/kriterin başarısızdan başarılıya geçişini yeniden ölç."""
    from .plan_checkpoint import _digest
    from .step_verification import evaluate_file_check

    verification = deps.lesson_state.verification if deps.lesson_state else None
    binding = advice.binding
    if verification is None or binding is None:
        return ()
    before = binding.criterion
    after = _digest(deps.tool_context.root, before.check_target)
    if not after or after == binding.before_digest:
        return ()
    check = VerificationCheck(
        before.criterion_id, before.kind, before.check_target, before.check_expected
    )
    matches = [
        item for item in verification.evidence if _criterion_key(item) == _criterion_key(before)
    ]
    if (
        len(matches) != 1
        or not matches[0].applicable
        or matches[0].status is not EvidenceStatus.PASSED
    ):
        return ()
    measured = evaluate_file_check(check, deps.tool_context.root)
    if not measured.applicable or measured.status is not EvidenceStatus.PASSED:
        return ()
    return (f"{before.criterion_id}:{after}",)


def settle_advice(outcome: AgentOutcome, deps: AgentDeps) -> None:
    """Tavsiye sonrası ilgili dosya değişikliği ve son kriter aynı bağı doğrular."""
    from .teacher_notebook import append_outcome

    pending, deps.pending_advice = deps.pending_advice, []
    verification = deps.lesson_state.verification if deps.lesson_state else None
    eligible = (
        deps.lessons is not None
        and verification is not None
        and verification.ok
        and not verification.failure_evidence
        and outcome.ok
        and not outcome.model_error
        and not outcome.budget_stopped
        and not outcome.hit_step_limit
    )
    for advice in pending:
        unique = (
            advice.binding is not None
            and sum(
                item.binding is not None
                and _criterion_key(item.binding.criterion)
                == _criterion_key(advice.binding.criterion)
                for item in pending
            )
            == 1
        )
        refs = _advice_refs(advice, deps) if eligible and unique else ()
        written = False
        if refs and deps.lessons is not None:
            written, _ = sync_teacher_lesson(
                deps.lessons,
                question=advice.question,
                answer=advice.answer,
                metadata=Lesson(
                    text=advice.answer[:_LESSON_TEXT_LIMIT],
                    kind=LessonKind.SUCCESS,
                    task=advice.question,
                    source=LessonSource.TEACHER,
                    source_split=deps.lesson_context.policy.source_split,
                    verified_at=str(deps.clock.now()),
                    evidence_refs=(advice.advice_id, *refs),
                ),
            )
        deps.publisher.publish(TeacherAdviceOutcome(advice.advice_id, bool(refs), refs))
        append_outcome(deps.tool_context.root, advice.advice_id, refs, written)

"""Öneri turu — eklemeli aday üret, optimizasyon kümesinde ölç, AYRI kümede doğrula, öner.

Kendini geliştirme döngüsünün ikinci halkası. Bu akış istem dosyasını DEĞİŞTİRMEZ; tek
çıktısı bir `Proposal`dır ve uygulamak kullanıcı kararıdır (`apply.py`).

Aşırı uyum (DSPy uyarısı) iki katmanla sınırlanır:
1. Optimizasyon ve ayrı küme aynı görevleri paylaşıyorsa tur HİÇ başlamaz (model çağrısı
   harcanmadan reddedilir).
2. Optimizasyon kümesinde kazanan aday, ayrı kümede temelden KÖTÜ ise ya da eskiden geçen
   tek bir görevi bozuyorsa öneri olarak kaydedilmez.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from evals.compare import compare_reports
from evals.dongu_kaydi import OLAY_ONERI, kayit_ekle
from evals.metrics import RunReport
from evals.tasks import EvalTask
from evals.taslak import sadelestir

from fusion_cli.core.errors import EvalError

from .additive import AdditiveGenerator, FailureNote, SnippetProvider, addition_of
from .optimizer import DEFAULT_VARIANT_COUNT, PromptEvaluator, search
from .proposals import Proposal, ProposalStore, proposal_id, text_digest
from .selection import DEFAULT_MIN_IMPROVEMENT

#: Her iki kümede olması gereken en az görev sayısı; bir iki görevlik küme ölçüm değil şanstır.
MIN_SUITE_TASKS = 3

OUTCOME_PROPOSED = "onerildi"
OUTCOME_NO_GAIN = "iyilestirme_yok"
OUTCOME_NO_CANDIDATE = "gecen_aday_yok"
OUTCOME_HELDOUT_REGRESSION = "ayri_kume_gerilemesi"


class OverfitError(EvalError):
    """Optimizasyon ve ayrı küme aynı ölçümü yapıyor: sonuç aşırı uyumu gizler."""


@dataclass(frozen=True, slots=True)
class RoundResult:
    """Bir öneri turunun sonucu ve skorları (kayıt dosyasına da bunlar yazılır)."""

    outcome: str
    detail: str
    opt_base: float
    opt_candidate: float | None = None
    heldout_base: float | None = None
    heldout_candidate: float | None = None
    proposal: Proposal | None = None


@dataclass(frozen=True, slots=True)
class RoundSetup:
    """Bir öneri turunun girdileri (sabit bağlam)."""

    prompt: str
    base_text: str
    suite: str
    heldout_suite: str
    opt_tasks: tuple[EvalTask, ...]
    heldout_tasks: tuple[EvalTask, ...]
    log_path: Path
    now: Callable[[], float]
    timestamp: Callable[[float], str]
    variant_count: int = DEFAULT_VARIANT_COUNT
    min_improvement: float = DEFAULT_MIN_IMPROVEMENT
    min_tasks: int = MIN_SUITE_TASKS


def check_heldout(
    opt_tasks: tuple[EvalTask, ...], heldout_tasks: tuple[EvalTask, ...], *, min_tasks: int
) -> None:
    """Ayrı küme gerçekten ayrı mı: boş değil, yeterince büyük, görev/istek ortak değil."""

    for ad, tasks in (("optimizasyon", opt_tasks), ("ayrı", heldout_tasks)):
        if len(tasks) < min_tasks:
            raise OverfitError(
                f"{ad} kümesi en az {min_tasks} görev içermeli ({len(tasks)} var); "
                "bu kadar küçük bir kümede skor farkı şanstan ayırt edilemez"
            )
    ortak_id = {t.id for t in opt_tasks} & {t.id for t in heldout_tasks}
    ortak_istek = {sadelestir(t.request) for t in opt_tasks} & {
        sadelestir(t.request) for t in heldout_tasks
    }
    if ortak_id or ortak_istek:
        raise OverfitError(
            "optimizasyon ve ayrı küme aynı görevleri içeriyor "
            f"({len(ortak_id | ortak_istek)} ortak); ayrı küme optimizasyonda hiç görülmemiş "
            "olmalı, aksi halde aşırı uyum ölçülemez"
        )


async def run_round(
    setup: RoundSetup,
    *,
    provider: SnippetProvider,
    opt_evaluator: PromptEvaluator,
    heldout_evaluator: PromptEvaluator,
    store: ProposalStore,
) -> RoundResult:
    """Tek öneri turu. Model çağrıları yalnız enjekte edilen sağlayıcı/değerlendiriciden gelir."""

    check_heldout(setup.opt_tasks, setup.heldout_tasks, min_tasks=setup.min_tasks)
    base_report = await opt_evaluator.evaluate(setup.base_text)
    opt_base = base_report.task_success_rate
    if not base_report.results or opt_base >= 1.0:
        detail = "temel istem optimizasyon kümesinin hepsini zaten geçiyor"
        return _finish(setup, RoundResult(OUTCOME_NO_GAIN, detail, opt_base))

    generator = AdditiveGenerator(provider, failures=_failures(setup.opt_tasks, base_report))
    found = await search(
        setup.prompt,
        setup.base_text,
        generator=generator,
        evaluator=opt_evaluator,
        baseline_report=base_report,
        variant_count=setup.variant_count,
        min_improvement=setup.min_improvement,
    )
    winner_report = found.winner_report
    if winner_report is None:
        return _finish(setup, RoundResult(OUTCOME_NO_CANDIDATE, found.selection.reason, opt_base))

    candidate_text = found.selection.winner.text
    heldout_base = await heldout_evaluator.evaluate(setup.base_text)
    heldout_candidate = await heldout_evaluator.evaluate(candidate_text)
    scores = RoundResult(
        outcome=OUTCOME_HELDOUT_REGRESSION,
        detail="",
        opt_base=opt_base,
        opt_candidate=winner_report.task_success_rate,
        heldout_base=heldout_base.task_success_rate,
        heldout_candidate=heldout_candidate.task_success_rate,
    )
    problem = _heldout_problem(heldout_base, heldout_candidate)
    if problem:
        return _finish(setup, replace(scores, detail=problem))

    proposal = _build_proposal(setup, candidate_text, scores, found.selection.reason)
    store.save(proposal)
    done = replace(
        scores, outcome=OUTCOME_PROPOSED, detail=found.selection.reason, proposal=proposal
    )
    return _finish(setup, done)


def _build_proposal(
    setup: RoundSetup, candidate_text: str, scores: RoundResult, reason: str
) -> Proposal:
    return Proposal(
        id=proposal_id(setup.prompt, candidate_text),
        prompt=setup.prompt,
        created=setup.timestamp(setup.now()),
        suite=setup.suite,
        heldout_suite=setup.heldout_suite,
        base_digest=text_digest(setup.base_text),
        base_text=setup.base_text,
        candidate_text=candidate_text,
        addition=addition_of(setup.base_text, candidate_text),
        opt_base=scores.opt_base,
        opt_candidate=scores.opt_candidate or 0.0,
        heldout_base=scores.heldout_base or 0.0,
        heldout_candidate=scores.heldout_candidate or 0.0,
        reason=reason,
    )


def _heldout_problem(base: RunReport, candidate: RunReport) -> str:
    """Ayrı kümede aday temelden kötüyse nedeni; sorun yoksa boş metin."""

    regressions = compare_reports(base, candidate).regressions
    if regressions:
        return f"ayrı kümede eskiden geçen görev bozuldu: {', '.join(regressions)}"
    if candidate.task_success_rate < base.task_success_rate:
        return (
            f"ayrı kümede başarı oranı düştü ({base.task_success_rate:.2f} → "
            f"{candidate.task_success_rate:.2f})"
        )
    return ""


def _failures(tasks: tuple[EvalTask, ...], report: RunReport) -> tuple[FailureNote, ...]:
    by_id = {task.id: task for task in tasks}
    return tuple(
        FailureNote(result.task_id, by_id[result.task_id].request)
        for result in report.results
        if not result.success and result.task_id in by_id
    )


def _finish(setup: RoundSetup, result: RoundResult) -> RoundResult:
    kayit_ekle(
        setup.log_path,
        OLAY_ONERI,
        {
            "istem": setup.prompt,
            "kume": setup.suite,
            "ayri_kume": setup.heldout_suite,
            "sonuc": result.outcome,
            "opt_temel": result.opt_base,
            "opt_skoru": result.opt_candidate,
            "ayri_temel": result.heldout_base,
            "heldout_skoru": result.heldout_candidate,
            "oneri": result.proposal.id if result.proposal else None,
        },
        simdi=setup.now(),
    )
    return result

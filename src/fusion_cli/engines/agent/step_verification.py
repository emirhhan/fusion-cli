"""Plan adımlarını model beyanından bağımsız post-condition'larla doğrular."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.execution_plan import ExecutionPlan, PlanStep, StepStatus
from ...core.verification import VerificationResult

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


@dataclass(frozen=True, slots=True)
class StepVerificationResult:
    """Bir plan adımının kanıtları ve engelleyici bulguları."""

    ok: bool
    evidence: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()


def _safe_effect_path(root: Path, raw_path: str) -> Path | None:
    """Dosya post-condition yolunu çalışma kökü içinde çöz."""
    root = root.resolve()
    candidate = (root / raw_path).resolve()
    return candidate if candidate.is_relative_to(root) else None


async def verify_step(
    step: PlanStep,
    outcome: AgentOutcome,
    deps: AgentDeps,
) -> StepVerificationResult:
    """Agent sonucunu, beklenen etkileri ve proje kapısını birlikte doğrula."""
    evidence: list[str] = []
    findings: list[str] = []

    if not outcome.ok:
        findings.append("agent adımı başarısız sonuçlandırdı")
    if outcome.hit_step_limit:
        findings.append("agent adım bütçesi doldu")

    for effect in step.expected_effects:
        if effect.startswith("file:"):
            raw_path = effect.removeprefix("file:").strip()
            path = _safe_effect_path(deps.tool_context.root, raw_path)
            if path is None:
                findings.append(f"beklenen dosya çalışma kökü dışında: {raw_path}")
            elif not path.is_file():
                findings.append(f"beklenen dosya bulunamadı: {raw_path}")
            else:
                evidence.append(f"beklenen dosya bulundu: {raw_path}")
        elif effect == "workspace_mutation":
            if outcome.mutating_tool_calls_made <= 0:
                findings.append("beklenen çalışma alanı değişikliği gözlenmedi")
            else:
                evidence.append("çalışma alanı değişikliği araç kaydıyla doğrulandı")
        elif effect in {"shell_action", "git_commit", "git_push"}:
            if outcome.tool_calls_made <= 0:
                findings.append(f"beklenen araç etkisi gözlenmedi: {effect}")
            else:
                evidence.append(f"araç etkisi kaydı bulundu: {effect}")

    if deps.verifier is not None:
        verification = await deps.verifier.verify()
        if verification.ok:
            evidence.append("proje doğrulama kapısı geçti")
        else:
            findings.extend(verification.findings)
            if not verification.findings and verification.summary:
                findings.append(verification.summary)

    if outcome.final_text.strip():
        evidence.append(f"agent raporu: {outcome.final_text.strip()[:1200]}")
    return StepVerificationResult(
        ok=not findings,
        evidence=tuple(evidence),
        findings=tuple(findings),
    )


async def verify_plan_acceptance(
    plan: ExecutionPlan,
    deps: AgentDeps,
) -> VerificationResult:
    """Tamamlanan planı son proje kapısından geçir."""
    incomplete = tuple(
        step.step_id for step in plan.steps if step.status is not StepStatus.COMPLETED
    )
    if incomplete:
        finding = f"tamamlanmamış plan adımları: {', '.join(incomplete)}"
        return VerificationResult(ok=False, summary=finding, findings=(finding,))
    if deps.verifier is None:
        return VerificationResult(ok=True, summary="tüm plan adımları doğrulandı")
    return await deps.verifier.verify()

"""Plan adımlarını model beyanından bağımsız post-condition'larla doğrular."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.execution_plan import ExecutionPlan, PlanStep, StepStatus
from ...core.verification import VerificationResult
from .verify_discovery import behavioral_commands

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
    baseline: tuple[str, ...] = (),
) -> StepVerificationResult:
    """Agent sonucunu, beklenen etkileri ve proje kapısını birlikte doğrula.

    `baseline`, plan BAŞLAMADAN önce proje kapısının verdiği bulgulardır. Onlar
    adımın suçu değildir ve adımı düşürmez.

    Ölçüldü: sıfırdan Godot projesi kuran plan HER adımda "no main scene defined"
    ile düştü. Proje henüz kurulmadığı için kapı zaten düşüyordu; adım o hatayı
    yaratmamıştı. Bu ayrım olmadan sıfırdan proje kurmak imkânsızdır. Kapının
    adım başına sorusu "BOZDUM mu"dur; "her şey bitti mi" sorusunu final kabul
    kapısı sorar ve orada tam temizlik aranır.
    """
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
            if outcome.mutating_tool_calls_made > 0:
                evidence.append("çalışma alanı değişikliği araç kaydıyla doğrulandı")
            elif outcome.already_done_calls > 0:
                # Ölçüldü (Godot koşusu): birinci adım sahneyi baştan sona kurdu;
                # aynı işi hedefleyen ikinci adımın her çağrısı yinelenen sayılıp
                # engellendi ve adım GEÇİLEMEZ hâle geldi. Zaten yapılmış iş bir
                # başarısızlık değildir; final kapısı çıktının hâlâ durduğunu
                # ayrıca ölçer.
                evidence.append(
                    "beklenen değişiklik bu turda daha önce yapılmış "
                    "(yinelenen çağrılar engellendi)"
                )
            else:
                findings.append("beklenen çalışma alanı değişikliği gözlenmedi")
        elif effect in {"shell_action", "git_commit", "git_push"}:
            if outcome.tool_calls_made > 0:
                evidence.append(f"araç etkisi kaydı bulundu: {effect}")
            elif outcome.already_done_calls > 0:
                # `workspace_mutation` ile AYNI ilke: adım, işini önceki bir adım
                # yaptığı için yeni bir çağrı üretemeyebilir. Ölçüldü (Godot
                # koşusu): doğrulama komutu birinci adımda çıkış 0 ile çalıştı;
                # üçüncü adım sonucu göremediği için tekrar istedi, yinelenen
                # sayılıp engellendi ve kanıt üretemeden düştü.
                evidence.append(
                    f"beklenen etki bu turda daha önce gerçekleşti: {effect} "
                    "(yinelenen çağrılar engellendi)"
                )
            else:
                findings.append(f"beklenen araç etkisi gözlenmedi: {effect}")

    if deps.verifier is not None:
        verification = await deps.verifier.verify()
        if verification.ok:
            evidence.append("proje doğrulama kapısı geçti")
        else:
            onceden = set(baseline)
            yeni = tuple(bulgu for bulgu in verification.findings if bulgu not in onceden)
            if not yeni and verification.summary and verification.summary not in onceden:
                yeni = (verification.summary,)
            if yeni:
                findings.extend(yeni)
            else:
                evidence.append(
                    "proje kapısı bu adımdan ÖNCE de düşüyordu; adım yeni bir "
                    "kırılma eklemedi"
                )

    if outcome.final_text.strip():
        evidence.append(f"agent raporu: {outcome.final_text.strip()[:1200]}")
    return StepVerificationResult(
        ok=not findings,
        evidence=tuple(evidence),
        findings=tuple(findings),
    )


#: Yalnızca yapısal kapısı olan projede kullanıcıya ve modele verilen uyarı.
#:
#: Ölçülen hata: dört adımlık bir Godot planı "tamamlandı" dedi ve kabul kapısı
#: geçti; kapı `godot --headless --path . --quit` idi ve projenin AÇILDIĞINI
#: kanıtlıyordu. Üretilen scriptler hiçbir düğüme bağlanmamıştı, oyun hiç
#: çalışmıyordu. Kusur Godot'a özgü değildir: derleme, tip denetimi ve lint de
#: çıktının İYİ BİÇİMLİ olduğunu kanıtlar, İSTENEN İŞİ yaptığını değil.
#:
#: İş kırılmaz — testi olmayan her projede plan hiç tamamlanamazdı. Ama Fusion
#: kanıtlamadığı bir şeyi kanıtlanmış gibi SUNMAZ.
UNPROVEN_BEHAVIOR_WARNING = (
    "davranış kanıtlanmadı: bu projede kodu çalıştıran bir doğrulama komutu yok. "
    "Mevcut kapı yalnızca çıktının iyi biçimli olduğunu (derlenir/açılır) gösterir. "
    "Gerçek kanıt için projeye çalıştırılabilir bir test/kontrol komutu ekleyin."
)


def _stale_step_effects(plan: ExecutionPlan, root: Path) -> tuple[str, ...]:
    """Tamamlanmış adımların dosya post-condition'ları HÂLÂ duruyor mu?

    Adım kanıtı üretildiği ANDA doğrudur; plan ilerledikçe sonraki bir adım o
    çıktıyı silebilir ya da üzerine yazabilir. Final kapısı bunu sonda yeniden
    ölçmezse, eski bir "doğrulandı" kaydı eksik teslimi örtbas eder.
    """
    findings: list[str] = []
    for step in plan.steps:
        for effect in step.expected_effects:
            if not effect.startswith("file:"):
                continue
            raw_path = effect.removeprefix("file:").strip()
            path = _safe_effect_path(root, raw_path)
            if path is None or not path.is_file():
                findings.append(
                    f"adım çıktısı artık yok: {raw_path} ({step.step_id})"
                )
    return tuple(findings)


async def verify_plan_acceptance(
    plan: ExecutionPlan,
    deps: AgentDeps,
) -> VerificationResult:
    """Tamamlanan planı son kapıdan geçir ve neyin KANITLANMADIĞINI da söyle."""
    incomplete = tuple(
        step.step_id for step in plan.steps if step.status is not StepStatus.COMPLETED
    )
    if incomplete:
        finding = f"tamamlanmamış plan adımları: {', '.join(incomplete)}"
        return VerificationResult(ok=False, summary=finding, findings=(finding,))

    stale = _stale_step_effects(plan, deps.tool_context.root)
    if stale:
        return VerificationResult(ok=False, summary=stale[0], findings=stale)

    warnings = (
        () if behavioral_commands(deps.tool_context.root) else (UNPROVEN_BEHAVIOR_WARNING,)
    )
    if deps.verifier is None:
        return VerificationResult(
            ok=True, summary="tüm plan adımları doğrulandı", warnings=warnings
        )
    result = await deps.verifier.verify()
    if not result.ok:
        return result
    return replace(result, warnings=result.warnings + warnings)

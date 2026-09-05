"""Plan adımlarını model beyanından bağımsız post-condition'larla doğrular."""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.execution_plan import (
    ExecutionPlan,
    PlanStep,
    StepStatus,
    VerificationCheck,
    VerificationCheckKind,
)
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
    criteria: tuple[CriterionEvidence, ...] = ()

    @property
    def unverified(self) -> bool:
        """En az bir başarı koşulu için gerçek kanıt yok mu."""
        return any(item.status is EvidenceStatus.UNVERIFIED for item in self.criteria)


def _safe_effect_path(root: Path, raw_path: str) -> Path | None:
    """Dosya post-condition yolunu çalışma kökü içinde çöz."""
    root = root.resolve()
    candidate = (root / raw_path).resolve()
    return candidate if candidate.is_relative_to(root) else None


def _tool_command(use: object) -> str:
    """ToolUse üzerindeki desteklenen kabuk komutu alanını oku."""
    arguments = getattr(use, "arguments", {})
    if not isinstance(arguments, dict):
        try:
            arguments = dict(arguments)
        except (TypeError, ValueError):
            return ""
    for key in ("command", "cmd"):
        value = arguments.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def _contains_git_action(command: str, action: str) -> bool:
    """Kabuk segmentinde gerçek ve dry-run olmayan `git <action>` çağrısı var mı."""
    if "\n" in command:
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    if any(token in {";", "&", "&&", "|", "||"} for token in tokens):
        return False
    long_dry_run = any(token.startswith("--dry-run") for token in tokens)
    push_short_dry_run = action == "push" and any(
        token.startswith("-") and not token.startswith("--") and "n" in token[1:]
        for token in tokens
    )
    dry_run = long_dry_run or push_short_dry_run
    return _git_subcommand(tokens) == action and not dry_run


def _git_subcommand(tokens: list[str]) -> str:
    """İzin verilen sarmalayıcılardan sonra git alt komutunu çıkar."""
    index = 0
    if index < len(tokens) and tokens[index] in {"sudo", "command"}:
        index += 1
    if index < len(tokens) and tokens[index] == "env":
        index += 1
        while index < len(tokens) and "=" in tokens[index] and not tokens[index].startswith("-"):
            index += 1
    if index >= len(tokens) or tokens[index] != "git":
        return ""
    index += 1
    options_with_value = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index].split("=", 1)[0]
        index += 2 if option in options_with_value and "=" not in tokens[index - 1] else 1
    return tokens[index].casefold() if index < len(tokens) else ""


def _successful_tool_evidence(outcome: AgentOutcome, effect: str) -> CriterionEvidence | None:
    """Bir dış etkiyi adı ve argümanıyla gerçek başarılı çağrıya bağla."""
    for use in outcome.tool_uses:
        if not use.ok:
            continue
        command = _tool_command(use)
        matches = (
            (effect == "shell_action" and use.name == "run_shell")
            or (
                effect == "git_commit"
                and use.name == "run_shell"
                and _contains_git_action(command, "commit")
            )
            or (
                effect == "git_push"
                and use.name == "run_shell"
                and _contains_git_action(command, "push")
            )
        )
        if matches:
            return CriterionEvidence(
                criterion_id=effect,
                kind=VerificationCheckKind.COMMAND,
                status=EvidenceStatus.PASSED,
                summary=f"araç etkisi gerçek çağrıyla doğrulandı: {effect}",
                command=command,
                output=use.output[:8_000],
            )
    return None


def _legacy_file_check(step: PlanStep, criterion: str) -> VerificationCheck | None:
    """Eski planlardaki açık dosya-varlığı koşulunu güvenle dönüştür."""
    lowered = criterion.casefold()
    existence_words = ("bulun", "mevcut", "oluştur", "exists", "var")
    file_words = ("dosya", "file")
    if not any(word in lowered for word in existence_words) or not any(
        word in lowered for word in file_words
    ):
        return None
    paths = tuple(
        effect.removeprefix("file:").strip()
        for effect in step.expected_effects
        if effect.startswith("file:")
    )
    if len(paths) != 1:
        return None
    return VerificationCheck(
        criterion_id=criterion,
        kind=VerificationCheckKind.FILE_EXISTS,
        target=paths[0],
    )


def _command_evidence(
    command: str,
    outcome: AgentOutcome,
    verification: VerificationResult | None,
) -> CriterionEvidence | None:
    for use in outcome.tool_uses:
        if use.ok and use.name == "run_shell" and _tool_command(use) == command:
            return CriterionEvidence(
                criterion_id=command,
                kind=VerificationCheckKind.COMMAND,
                status=EvidenceStatus.PASSED,
                summary="komut güvenli araç yolundan başarıyla çalıştı",
                command=command,
                output=use.output[:8_000],
            )
    if verification is None:
        return None
    return next(
        (
            item
            for item in verification.evidence
            if item.kind is VerificationCheckKind.COMMAND and item.command == command
        ),
        None,
    )


def _evaluate_check(
    check: VerificationCheck,
    *,
    root: Path,
    outcome: AgentOutcome,
    verification: VerificationResult | None,
) -> CriterionEvidence:
    """Tek kontrolü yürüt; yeni komut başlatmadan yalnız mevcut kanıtı tüket."""
    if check.kind in {VerificationCheckKind.FILE_EXISTS, VerificationCheckKind.FILE_CONTAINS}:
        return _evaluate_file_check(check, root)

    if check.kind is VerificationCheckKind.COMMAND:
        found = _command_evidence(check.target, outcome, verification)
        if found is not None:
            return replace(found, criterion_id=check.criterion_id)
        return CriterionEvidence(
            check.criterion_id,
            check.kind,
            EvidenceStatus.UNVERIFIED,
            "komutun çalıştırıldığına ilişkin kayıt yok",
            command=check.target,
        )

    expected_arguments = _expected_tool_arguments(check.expected)
    if expected_arguments is None:
        return CriterionEvidence(
            check.criterion_id,
            check.kind,
            EvidenceStatus.UNVERIFIED,
            "araç kontrolünde beklenen argümanlar geçerli JSON nesnesi değil",
        )
    for use in outcome.tool_uses:
        if (
            use.name == check.target
            and use.ok
            and all(use.arguments.get(key) == value for key, value in expected_arguments.items())
        ):
            return CriterionEvidence(
                check.criterion_id,
                check.kind,
                EvidenceStatus.PASSED,
                "araç çağrısı başarıyla çalıştı",
                output=use.output[:8_000],
            )
    return CriterionEvidence(
        check.criterion_id,
        check.kind,
        EvidenceStatus.UNVERIFIED,
        "başarılı araç çağrısı kaydı yok",
    )


def _evaluate_file_check(check: VerificationCheck, root: Path) -> CriterionEvidence:
    """Dosya kontrolünü gerçek artifact üzerinde yeniden ölç."""
    path = _safe_effect_path(root, check.target)
    if path is None:
        return CriterionEvidence(
            check.criterion_id,
            check.kind,
            EvidenceStatus.FAILED,
            "kontrol hedefi çalışma kökü dışında",
            artifact=check.target,
        )
    if not path.is_file():
        return CriterionEvidence(
            check.criterion_id,
            check.kind,
            EvidenceStatus.FAILED,
            "kontrol hedefi dosya bulunamadı",
            artifact=check.target,
        )
    if check.kind is VerificationCheckKind.FILE_EXISTS:
        return CriterionEvidence(
            check.criterion_id,
            check.kind,
            EvidenceStatus.PASSED,
            "dosya varlığı doğrulandı",
            artifact=check.target,
        )
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return CriterionEvidence(
            check.criterion_id,
            check.kind,
            EvidenceStatus.UNVERIFIED,
            f"dosya içeriği okunamadı: {exc}",
            artifact=check.target,
        )
    status = EvidenceStatus.PASSED if check.expected in content else EvidenceStatus.FAILED
    return CriterionEvidence(
        check.criterion_id,
        check.kind,
        status,
        "beklenen içerik bulundu"
        if status is EvidenceStatus.PASSED
        else "beklenen içerik bulunamadı",
        artifact=check.target,
    )


def _expected_tool_arguments(raw: str) -> dict[str, object] | None:
    """TOOL kontrolündeki JSON argüman alt kümesini ayrıştır."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    return value


def _criterion_evidence(
    step: PlanStep,
    *,
    root: Path,
    outcome: AgentOutcome,
    verification: VerificationResult | None,
) -> tuple[CriterionEvidence, ...]:
    """Her başarı koşulunu bağlı kontrollerle değerlendir."""
    results: list[CriterionEvidence] = []
    for criterion in step.success_criteria:
        checks = tuple(
            check for check in step.verification_checks if check.criterion_id == criterion
        )
        if not checks:
            legacy = _legacy_file_check(step, criterion)
            checks = (legacy,) if legacy is not None else ()
        if not checks:
            results.append(
                CriterionEvidence(
                    criterion,
                    VerificationCheckKind.TOOL,
                    EvidenceStatus.UNVERIFIED,
                    "başarı koşuluna bağlı tipli kontrol yok",
                )
            )
            continue
        checked = tuple(
            _evaluate_check(
                check,
                root=root,
                outcome=outcome,
                verification=verification,
            )
            for check in checks
        )
        failed = next((item for item in checked if item.status is EvidenceStatus.FAILED), None)
        unverified = next(
            (item for item in checked if item.status is EvidenceStatus.UNVERIFIED),
            None,
        )
        representative = failed or unverified or checked[-1]
        results.append(representative)
    return tuple(results)


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

    verification = await deps.verifier.verify() if deps.verifier is not None else None

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
            effect_evidence = _successful_tool_evidence(outcome, effect)
            if effect_evidence is None:
                findings.append(f"beklenen araç etkisi doğrulanamadı: {effect}")
            else:
                evidence.append(effect_evidence.summary)

    if verification is not None:
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
                    "proje kapısı bu adımdan ÖNCE de düşüyordu; adım yeni bir kırılma eklemedi"
                )

    criteria = _criterion_evidence(
        step,
        root=deps.tool_context.root,
        outcome=outcome,
        verification=verification,
    )
    for item in criteria:
        if item.status is EvidenceStatus.PASSED:
            evidence.append(f"başarı koşulu doğrulandı: {item.criterion_id}")
        elif item.status is EvidenceStatus.FAILED:
            findings.append(f"başarı koşulu başarısız: {item.criterion_id} ({item.summary})")
        else:
            evidence.append(f"başarı koşulu doğrulanamadı: {item.criterion_id} ({item.summary})")

    if outcome.final_text.strip():
        evidence.append(f"agent raporu: {outcome.final_text.strip()[:1200]}")
    return StepVerificationResult(
        ok=not findings,
        evidence=tuple(evidence),
        findings=tuple(findings),
        criteria=criteria,
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
                findings.append(f"adım çıktısı artık yok: {raw_path} ({step.step_id})")
        for check in step.verification_checks:
            if check.kind not in {
                VerificationCheckKind.FILE_EXISTS,
                VerificationCheckKind.FILE_CONTAINS,
            }:
                continue
            result = _evaluate_file_check(check, root)
            if result.status is not EvidenceStatus.PASSED:
                findings.append(
                    f"başarı koşulu artık geçmiyor: {check.criterion_id} "
                    f"({check.expected or check.target}; {result.summary})"
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

    if deps.verifier is None:
        return VerificationResult(
            ok=True,
            summary="tüm plan adımları doğrulandı",
            warnings=(UNPROVEN_BEHAVIOR_WARNING,),
        )
    result = await deps.verifier.verify()
    if not result.ok:
        return result
    expected_behavior = set(behavioral_commands(deps.tool_context.root))
    behavior_proven = any(
        item.kind is VerificationCheckKind.COMMAND
        and item.status is EvidenceStatus.PASSED
        and item.command in expected_behavior
        for item in result.evidence
    )
    warnings = () if behavior_proven else (UNPROVEN_BEHAVIOR_WARNING,)
    return replace(result, warnings=result.warnings + warnings)

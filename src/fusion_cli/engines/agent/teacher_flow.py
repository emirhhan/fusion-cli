"""Kök tur başlamadan öğretmen planını mevcut araç akışına bağla."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.events import (
    StatusChanged,
    TeacherLessonRecorded,
    TeacherLimitationFound,
    TeacherMemoryUsed,
    TeacherPlanPrepared,
    TeacherTaskClassified,
    ToolExecuted,
    ToolOutcome,
)
from ...core.redaction import redact
from ...core.types import Message
from ...tools.diffing import bounded_diff
from ...tools.files import display_path
from ...tools.planning import todo_write
from .repo_context import repo_map_block
from .teacher_brief import BRIEF_CHAR_BUDGET
from .teacher_memory import find_reusable_plan, plan_steps_from_lesson, record_plan_outcome
from .teacher_plan import (
    TeacherPlanError,
    classify_teacher_task,
    parse_teacher_plan,
    parse_teacher_review,
)

if TYPE_CHECKING:
    from ...core.verification import VerificationResult
    from ...tools.registry import ToolRegistry
    from .loop import AgentDeps, AgentOutcome

# Yalnız standart proje manifestlerinin yapısı okunur; değerler gönderilmez.
# Kesit üst sınırı, mevcut öğretmen brief bütçesinin bir bölümüdür.
_MANIFESTS = ("pyproject.toml", "package.json", "Cargo.toml")
_MANIFEST_BUDGET = BRIEF_CHAR_BUDGET // 8
_RELATED_FILE_BUDGET = 4096


def _project_context(root: Path, task: str) -> str:
    """Kök yapıyı ve değer içermeyen, sınırlı manifest anahtarlarını derle."""
    entries = sorted(path.name for path in root.iterdir() if path.name != ".env")
    pieces = ["Kök dizin: " + ", ".join(entries), repo_map_block(root)]
    for name in _MANIFESTS:
        path = root / name
        if path.is_file() and not path.is_symlink():
            snippet = path.read_bytes()[:_MANIFEST_BUDGET].decode("utf-8", errors="ignore")
            if name == "package.json":
                keys = re.findall(r'^\s*"([^"\n]+)"\s*:', snippet, re.MULTILINE)
            else:
                sections = re.findall(r"^\s*\[([^\]\n]+)\]", snippet, re.MULTILINE)
                keys = sections + re.findall(
                    r"^\s*([A-Za-z_][\w.-]*)\s*=", snippet, re.MULTILINE
                )
            pieces.append(f"{name} anahtarları: {redact(', '.join(keys[:40]))}")
    # Kullanıcının açıkça andığı çalışma alanı dosyalarını yalnız göreli adlarıyla
    # göster. İçerikleri bilinmeyen dosyalar öğretmene kopyalanmaz.
    referenced = sorted(set(re.findall(r"[\w./-]+\.(?:py|tsx?|jsx?|md)", task)))
    for name in referenced:
        path = (root / name).resolve()
        if path.is_relative_to(root.resolve()) and path.is_file():
            snippet = path.read_bytes()[:_RELATED_FILE_BUDGET].decode("utf-8", errors="ignore")
            definitions = re.findall(
                r"^\s*(?:async\s+def|def|class|function|export\s+(?:function|class|const))\s+([A-Za-z_][\w]*)",
                snippet,
                re.MULTILINE,
            )
            summary = ", ".join(definitions[:20]) or "tanım bulunamadı"
            pieces.append(f"İlgili dosya: {name}; tanımlar: {redact(summary)}")
    return "\n".join(piece for piece in pieces if piece)


def teacher_is_ready(deps: AgentDeps, registry: ToolRegistry) -> bool:
    """Yalnız giriş doğrulanmış etkin tarayıcı öğretmeni kullan."""
    teacher = deps.config.teacher
    return (
        not deps.teacher_unavailable_notified
        and teacher is not None
        and registry.get("ask_teacher") is not None
        and any(
            session.model == teacher.model
            and session.transport == "browser"
            and session.enabled
            and session.login_verified
            for session in deps.config.web_sessions
        )
    )


def _notify_unavailable(deps: AgentDeps, message: str) -> None:
    if deps.teacher_unavailable_notified:
        return
    deps.teacher_unavailable_notified = True
    deps.publisher.publish(StatusChanged(message=message))


async def _ask(registry: ToolRegistry, deps: AgentDeps, *, question: str, durum: str) -> str | None:
    deps.teacher_lesson_sync_deferred = True
    try:
        async with asyncio.timeout(deps.config.runtime.request_timeout_s):
            result = await registry.execute(
                "ask_teacher", {"question": question, "durum": durum}, deps.tool_context
            )
    except TimeoutError:
        _notify_unavailable(deps, "Öğretmen yanıtı zaman aşımına uğradı; tek başıma ilerliyorum.")
        return None
    finally:
        deps.teacher_lesson_sync_deferred = False
    deps.publisher.publish(
        ToolExecuted(
            name="ask_teacher",
            args={"question": question},
            outcome=ToolOutcome.OK if result.ok else ToolOutcome.FAILED,
            output=redact(result.output),
        )
    )
    if not result.ok:
        _notify_unavailable(deps, "Öğretmene ulaşılamadı; tek başıma ilerliyorum.")
        return None
    return result.output


async def prepare_teacher_plan(
    task: str, messages: list[Message], deps: AgentDeps, registry: ToolRegistry
) -> None:
    """Uygun kök görevde plan al; başarısızlıkta çırağı durdurma."""
    decision = classify_teacher_task(task)
    deps.publisher.publish(TeacherTaskClassified(size=decision.size, reasons=decision.reasons))
    if decision.size == "basit":
        return
    if _apply_remembered_plan(task, messages, deps):
        return
    if not teacher_is_ready(deps, registry):
        _notify_unavailable(deps, "Bağlı öğretmen yok; tek başıma ilerliyorum.")
        return
    context = await asyncio.to_thread(_project_context, deps.tool_context.root, task)
    question = (
        "İşe başlamadan uygulanabilir planı yalnız JSON olarak ver. Alanlar: "
        "adimlar (sıralı metin dizisi), dosyalar (metin dizisi), riskler "
        "(metin dizisi), yapilamayanlar (konu, gerekce, alternatif alanlı "
        "nesne dizisi), dogrulama (metin dizisi). Dış platform kısıtlarını "
        "gerekçesi ve uygulanabilir alternatifiyle belirt."
    )
    answer = await _ask(
        registry, deps, question=question, durum=redact(f"Görev: {task}\n\nProje: {context}")
    )
    if answer is None:
        return
    structured = True
    try:
        plan = parse_teacher_plan(answer)
    except TeacherPlanError:
        repair = await _ask(
            registry,
            deps,
            question="Önceki cevabını istenen alanlarla geçerli JSON planına düzelt.",
            durum=redact(answer),
        )
        try:
            plan = parse_teacher_plan(repair or "")
        except TeacherPlanError:
            structured = False
            messages.append(
                Message(
                    "user", f"FUSION_NOT: Öğretmen plan notu:\n{redact(answer)}",
                    harness_note=True,
                )
            )
            deps.publisher.publish(TeacherPlanPrepared(steps=0, structured=False))
            return
    deps.pending_teacher_plan = plan
    _publish_todos(plan.steps, deps)
    deps.platform_limitations.extend(plan.unworkables)
    for part in plan.unworkables:
        deps.publisher.publish(
            TeacherLimitationFound(
                topic=part.topic, reason=part.reason, alternative=part.alternative
            )
        )
        deps.publisher.publish(
            StatusChanged(
                message=(
                    f"{part.topic} yapılamıyor: {part.reason}. Alternatif: {part.alternative}."
                )
            )
        )
    messages.append(
        Message(
            "user",
            "FUSION_NOT: Öğretmen planı (uygula ve doğrula):\n" + redact(plan.raw),
            harness_note=True,
        )
    )
    deps.publisher.publish(TeacherPlanPrepared(steps=len(plan.steps), structured=structured))


def _publish_todos(steps: tuple[str, ...], deps: AgentDeps) -> None:
    """Plan adımlarını `todo_write` ile aynı yapıda görev listesine aktar."""
    from ...core.tools import TodoStatus

    items = [{"content": step, "status": TodoStatus.PENDING.value} for step in steps]
    todo_result = todo_write({"todos": items}, deps.tool_context)
    deps.publisher.publish(
        ToolExecuted(
            name="todo_write",
            args={"todos": items},
            outcome=ToolOutcome.OK,
            output=todo_result.output,
        )
    )


def _lessons_enabled(deps: AgentDeps) -> bool:
    return deps.lessons is not None and deps.config.runtime.lessons


def _apply_remembered_plan(task: str, messages: list[Message], deps: AgentDeps) -> bool:
    """Benzer görevin başarılı planı varsa öğretmene sormadan onu uygula."""
    if not _lessons_enabled(deps):
        return False
    from .learning_steps import _workspace, lesson_tags

    assert deps.lessons is not None
    found = find_reusable_plan(
        deps.lessons, task, workspace=_workspace(deps), tags=lesson_tags(deps)
    )
    if found is None:
        return False
    lesson, similarity = found
    steps = plan_steps_from_lesson(lesson.text)
    deps.reused_teacher_lesson = lesson
    _publish_todos(steps, deps)
    messages.append(
        Message(
            "user",
            "FUSION_NOT: Hafızadan: geçen sefer benzer bir işi "
            f"(\"{lesson.task}\") şu planla başarıyla yapmıştık. Bu göreve uyarlayarak "
            "izle, uymayan adımı atla ve sonucu doğrula:\n" + redact(lesson.text),
            harness_note=True,
        )
    )
    deps.publisher.publish(TeacherMemoryUsed(steps=len(steps), similarity=round(similarity, 2)))
    deps.publisher.publish(StatusChanged(message="Hafızadan ilerliyorum; öğretmene sorulmadı."))
    return True


def settle_teacher_plan(
    task: str,
    outcome: AgentOutcome,
    deps: AgentDeps,
    *,
    verification: VerificationResult | None,
) -> None:
    """Turun sonucunu bu turda kullanılan öğretmen planına işle.

    Hafızadan gelen plan başarı/başarısızlığa göre güçlenir ya da zayıflar;
    öğretmenden yeni alınan plan yalnız başarılı turda derse dönüşür.
    """
    from .learning_steps import _workspace, lesson_tags
    from .verification import resolve_turn_success

    reused, fresh = deps.reused_teacher_lesson, deps.pending_teacher_plan
    deps.reused_teacher_lesson = deps.pending_teacher_plan = None
    if not _lessons_enabled(deps) or (reused is None and fresh is None):
        return
    assert deps.lessons is not None
    success = resolve_turn_success(
        outcome_ok=outcome.ok, hit_step_limit=outcome.hit_step_limit, verification=verification
    )
    if reused is not None:
        if deps.lessons.reinforce((reused.text,), success=success):
            deps.publisher.publish(TeacherLessonRecorded(success=success, reused=True))
        return
    assert fresh is not None
    changed = len(deps.tool_context.changes.paths)
    gate = "geçti" if verification is not None and verification.ok else "çalışmadı"
    if record_plan_outcome(
        deps.lessons,
        task=task,
        plan=fresh,
        success=success,
        workspace=_workspace(deps),
        tags=lesson_tags(deps),
        evidence=f"{changed} dosya değişti; doğrulama kapısı {gate}",
    ):
        deps.publisher.publish(TeacherLessonRecorded(success=True, reused=False))


def _diff_summary(deps: AgentDeps) -> str:
    """Yalnız bu turun değişikliklerinden sınırlı ve maskelenmiş farklar üret."""
    summaries: list[str] = []
    for snapshot in deps.tool_context.changes.snapshots:
        try:
            current = snapshot.path.read_bytes()
        except OSError:
            continue
        if b"\x00" in current or (snapshot.content is not None and b"\x00" in snapshot.content):
            continue
        path = display_path(deps.tool_context, snapshot.path)
        old = (snapshot.content or b"").decode("utf-8", errors="replace")
        new = current.decode("utf-8", errors="replace")
        diff = bounded_diff(old, new, path)
        if diff:
            summaries.append(redact(diff))
    return "\n\n".join(summaries)


async def review_teacher_changes(
    outcome: AgentOutcome, deps: AgentDeps, registry: ToolRegistry
) -> tuple[str, ...] | None:
    """Dosya değişikliğini öğretmene denetlet; belirsiz yanıtı temiz sayma."""
    if not outcome.ok or not deps.tool_context.changes.paths:
        return None
    if not teacher_is_ready(deps, registry):
        return None
    tests = [
        redact(use.output)
        for use in outcome.tool_uses
        if use.name in {"run_shell", "bash", "shell"}
        and any(
            word in str(use.arguments.get("command", "")) for word in ("test", "pytest", "build")
        )
    ]
    durum = "Değişiklik farkı:\n" + await asyncio.to_thread(_diff_summary, deps)
    durum += "\n\nTest çıktısı:\n" + ("\n".join(tests) or "Test çıktısı kaydedilmedi.")
    answer = await _ask(
        registry,
        deps,
        question='Eksik veya yanlış var mı? Yalnız JSON {"bulgular": ["somut sorun"]} ver.',
        durum=durum,
    )
    if answer is None:
        return None
    try:
        return parse_teacher_review(answer)
    except TeacherPlanError:
        deps.publisher.publish(StatusChanged(message="Öğretmen denetimi ayrıştırılamadı."))
        return None

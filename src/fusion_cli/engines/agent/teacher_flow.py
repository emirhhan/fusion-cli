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
from ...core.tools import ToolFamily, tool_family
from ...core.types import Message
from ...tools.diffing import bounded_diff
from ...tools.files import display_path
from ...tools.planning import todo_write
from ...tools.search import is_secret_file
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


def _read_head(path: Path, limit: int) -> str:
    """Dosyanın yalnız ilk `limit` baytını oku (tamamı belleğe alınmaz; A4-29)."""
    with path.open("rb") as handle:
        return handle.read(limit).decode("utf-8", errors="ignore")


def _project_context(root: Path, task: str) -> str:
    """Kök yapıyı ve değer içermeyen, sınırlı manifest anahtarlarını derle."""
    # Olası kimlik dosyalarının (`.env.local`, `id_rsa`, `*.pem`, `credentials.json`) ADI da
    # üçüncü taraf öğretmene gitmez (A4-29).
    entries = sorted(
        path.name for path in root.iterdir() if not (path.is_file() and is_secret_file(path))
    )
    pieces = ["Kök dizin: " + ", ".join(entries), repo_map_block(root)]
    for name in _MANIFESTS:
        path = root / name
        if path.is_file() and not path.is_symlink():
            snippet = _read_head(path, _MANIFEST_BUDGET)
            if name == "package.json":
                keys = re.findall(r'^\s*"([^"\n]+)"\s*:', snippet, re.MULTILINE)
            else:
                sections = re.findall(r"^\s*\[([^\]\n]+)\]", snippet, re.MULTILINE)
                keys = sections + re.findall(r"^\s*([A-Za-z_][\w.-]*)\s*=", snippet, re.MULTILINE)
            pieces.append(f"{name} anahtarları: {redact(', '.join(keys[:40]))}")
    # Kullanıcının açıkça andığı çalışma alanı dosyalarını yalnız göreli adlarıyla
    # göster. İçerikleri bilinmeyen dosyalar öğretmene kopyalanmaz.
    referenced = sorted(set(re.findall(r"[\w./-]+\.(?:py|tsx?|jsx?|md)", task)))
    for name in referenced:
        path = (root / name).resolve()
        if path.is_relative_to(root.resolve()) and path.is_file():
            snippet = _read_head(path, _RELATED_FILE_BUDGET)
            definitions = re.findall(
                r"^\s*(?:async\s+def|def|class|function|export\s+(?:function|class|const))\s+([A-Za-z_][\w]*)",
                snippet,
                re.MULTILINE,
            )
            summary = ", ".join(definitions[:20]) or "tanım bulunamadı"
            pieces.append(f"İlgili dosya: {name}; tanımlar: {redact(summary)}")
    return "\n".join(piece for piece in pieces if piece)


#: Araç özetinde açıklamadan alınan en fazla karakter (ilk cümle çoğu araçta sığar).
_TOOL_SUMMARY_CHARS = 160


def _tool_summary(registry: ToolRegistry) -> str:
    """Çırağın araçları: öğretmen planı bunlara göre kursun."""
    lines = [
        f"- {tool.name}: {' '.join(tool.description.split())[:_TOOL_SUMMARY_CHARS]}"
        for tool in registry
        if tool.name != "ask_teacher"
    ]
    return "Çırağın araçları (plan adımları bunlarla uygulanır):\n" + "\n".join(lines)


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


#: Öğretmen cevabının modele eklenen en çok uzunluğu: 20k karakterlik düzyazı küçük bağlamlı
#: modelde bağlamı yiyordu (A4-32).
_TEACHER_NOTE_CHARS = 6_000

#: Öğretmenin "yapılamıyor" dediği konular KANITSIZ görüştür (A4-33): çırak kendi araçlarıyla
#: yapılabildiğini görürse denemelidir; yanlış bir kısıt yapılabilir işi kapatmasın.
_UNWORKABLE_CAVEAT = (
    "\n\nNot: 'yapılamıyor' denen konular öğretmenin GÖRÜŞÜDÜR, doğrulanmadı. Kendi "
    "araçlarınla yapılabildiğini gösteren kanıt bulursan dene ve sonucu raporla."
)


#: Bir soruda öğretmene en fazla bu kadar deneme yapılır (ilk deneme + 1 yeniden deneme).
#: İKİ ardışık başarısızlık öğretmeni o tur için kapatır; tek bir CAPTCHA, geçici ağ
#: hatası ya da bir kez yavaş cevap kalıcı kapanma sebebi DEĞİLDİR (A4-31).
_TEACHER_MAX_ATTEMPTS = 2


async def _ask(
    registry: ToolRegistry, deps: AgentDeps, *, question: str, durum: str, bicim: str = ""
) -> str | None:
    """Öğretmene tek soru sor; geçici hatada BİR kez yeniden dene.

    Ölçüldü (30 Ekim, A4-31): tek bir zaman aşımı ya da `ok=False` hemen
    `teacher_unavailable_notified` bayrağını kurup öğretmeni kapatıyordu. Bekleme de
    genel API zaman aşımına (`request_timeout_s`) bağlıydı; artık ayrı bir
    `teacher_timeout_s` var.
    """
    runtime = deps.config.runtime
    timeout_s = getattr(runtime, "teacher_timeout_s", runtime.request_timeout_s)
    for attempt in range(1, _TEACHER_MAX_ATTEMPTS + 1):
        last = attempt == _TEACHER_MAX_ATTEMPTS
        deps.teacher_lesson_sync_deferred = True
        try:
            async with asyncio.timeout(timeout_s):
                result = await registry.execute(
                    "ask_teacher",
                    {"question": question, "durum": durum, "bicim": bicim},
                    deps.tool_context,
                )
        except TimeoutError:
            if last:
                _notify_unavailable(
                    deps, "Öğretmen yanıtı zaman aşımına uğradı; tek başıma ilerliyorum."
                )
                return None
            deps.publisher.publish(
                StatusChanged(
                    message="Öğretmen yanıtı zaman aşımına uğradı; bir kez daha deniyorum."
                )
            )
            continue
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
        if result.ok:
            return result.output
        if (result.structured or {}).get("teacher") == "refused":
            # Oturum ayakta, yalnız bu soru cevaplanmadı: öğretmen tur boyunca kapatılmaz.
            deps.publisher.publish(
                StatusChanged(message="Öğretmen bu soruyu yanıtlamadı; plan olmadan ilerliyorum.")
            )
            return None
        if last:
            _notify_unavailable(deps, "Öğretmene ulaşılamadı; tek başıma ilerliyorum.")
            return None
        deps.publisher.publish(
            StatusChanged(message="Öğretmene ulaşılamadı; bir kez daha deniyorum.")
        )
    return None


async def prepare_teacher_plan(
    task: str, messages: list[Message], deps: AgentDeps, registry: ToolRegistry
) -> None:
    """Uygun kök görevde plan al; başarısızlıkta çırağı durdurma."""
    decision = classify_teacher_task(task)
    deps.publisher.publish(TeacherTaskClassified(size=decision.size, reasons=decision.reasons))
    if decision.size == "basit":
        return
    if await _apply_remembered_plan(task, messages, deps):
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
        registry,
        deps,
        question=question,
        durum=redact(f"Görev: {task}\n\nProje: {context}\n\n{_tool_summary(registry)}"),
        bicim="plan",
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
            question=(
                "Aşağıdaki önceki cevabını şu alanlarla geçerli tek bir JSON nesnesine çevir: "
                "adimlar, dosyalar, riskler, yapilamayanlar (konu, gerekce, alternatif), "
                "dogrulama. İçeriği değiştirme, yalnız biçimi düzelt."
            ),
            durum=redact(answer),
            bicim="plan",
        )
        try:
            plan = parse_teacher_plan(repair or "")
        except TeacherPlanError:
            structured = False
            messages.append(
                Message(
                    "user",
                    f"FUSION_NOT: Öğretmen plan notu:\n{redact(answer)[:_TEACHER_NOTE_CHARS]}",
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
            "FUSION_NOT: Öğretmen planı (uygula ve doğrula):\n"
            + redact(plan.raw)[:_TEACHER_NOTE_CHARS]
            + _UNWORKABLE_CAVEAT * bool(plan.unworkables),
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


async def _apply_remembered_plan(task: str, messages: list[Message], deps: AgentDeps) -> bool:
    """Benzer görevin başarılı planı varsa öğretmene sormadan onu uygula."""
    if not _lessons_enabled(deps):
        return False
    from .learning_steps import _workspace, lesson_tags

    if deps.lessons is None:  # `python -O` altında assert kalkardı
        return False
    # Chroma/embedding araması ilk çağrıda model yükleyebilir: olay döngüsünü bloklamasın (A4-38).
    found = await asyncio.to_thread(
        find_reusable_plan, deps.lessons, task, workspace=_workspace(deps), tags=lesson_tags(deps)
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
            f'("{lesson.task}") şu planla başarıyla yapmıştık. Bu göreve uyarlayarak '
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
    if deps.lessons is None:
        return
    success = resolve_turn_success(
        outcome_ok=outcome.ok, hit_step_limit=outcome.hit_step_limit, verification=verification
    )
    if reused is not None:
        if deps.lessons.reinforce((reused.text,), success=success):
            deps.publisher.publish(TeacherLessonRecorded(success=success, reused=True))
        return
    if fresh is None:
        return
    changed = len(deps.tool_context.changes.paths)
    gate = "çalışmadı" if verification is None else ("geçti" if verification.ok else "başarısız")
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


#: Öğretmene gönderilen fark için dosya başına en çok bayt.
_DIFF_FILE_MAX_BYTES = 512 * 1024


def _diff_summary(deps: AgentDeps) -> str:
    """Yalnız bu turun değişikliklerinden sınırlı ve maskelenmiş farklar üret."""
    summaries: list[str] = []
    for snapshot in deps.tool_context.changes.snapshots:
        # Olası kimlik/sır dosyalarının farkı üçüncü taraf öğretmene gitmez; desen maskeleme
        # yetmez (A4-30). Çok büyük dosya da sınırsız okunmaz.
        if is_secret_file(snapshot.path):
            continue
        try:
            with snapshot.path.open("rb") as handle:
                current = handle.read(_DIFF_FILE_MAX_BYTES + 1)
        except OSError:
            continue
        if len(current) > _DIFF_FILE_MAX_BYTES:
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


#: Test/derleme komutu: `latest`, `contest` gibi sözcüklerin içindeki "test" eşleşmesin (A4-56).
_TEST_COMMAND = re.compile(r"(?<![A-Za-z])(?:py)?test|(?<![A-Za-z])build")

#: Denetime giden görev metni sınırı: öğretmen brief bütçesinin (25k) küçük bir
#: kesri; gereksinim listeli uzun görevler (ölçülen örnek ~900 karakter) sığar.
_REVIEW_TASK_CHARS = BRIEF_CHAR_BUDGET // 6


async def review_teacher_changes(
    task: str, outcome: AgentOutcome, deps: AgentDeps, registry: ToolRegistry
) -> tuple[str, ...] | None:
    """Dosya değişikliğini görev gereksinimlerine karşı öğretmene denetlet.

    Görev metni pakete girer. Ölçüldü (30 Eylül, canlı): yalnız fark ve test
    çıktısını gören öğretmen "maliyet tabanı yukarı yuvarlanır" gereksinimini
    göremedi, gizli testte düşen hatayı temiz buldu ve tur sahte başarıyla bitti.
    Belirsiz yanıt temiz sayılmaz.
    """
    if not outcome.ok or not deps.tool_context.changes.paths:
        return None
    if not teacher_is_ready(deps, registry):
        return None
    tests = [
        redact(use.output)
        for use in outcome.tool_uses
        if tool_family(use.name) is ToolFamily.SHELL
        and _TEST_COMMAND.search(str(use.arguments.get("command", "")))
    ]
    durum = "Görev ve gereksinimler:\n" + redact(task)[:_REVIEW_TASK_CHARS]
    durum += "\n\nDeğişiklik farkı:\n" + await asyncio.to_thread(_diff_summary, deps)
    durum += "\n\nTest çıktısı:\n" + ("\n".join(tests) or "Test çıktısı kaydedilmedi.")
    answer = await _ask(
        registry,
        deps,
        question=(
            "Görevdeki her gereksinimi farka karşı tek tek kontrol et; sayısal kural "
            "ve kenar durumlarını örnek değerle dene. Karşılanmayan ya da yanlış "
            'uygulanan gereksinim var mı? Yalnız JSON {"bulgular": ["somut sorun"]} ver.'
        ),
        durum=durum,
    )
    if answer is None:
        return None
    try:
        return parse_teacher_review(answer)
    except TeacherPlanError:
        deps.publisher.publish(StatusChanged(message="Öğretmen denetimi ayrıştırılamadı."))
        return None

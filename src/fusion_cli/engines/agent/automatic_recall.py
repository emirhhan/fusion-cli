"""İsteğe bağlı otomatik ders okuması: tek daemon worker, sınırlı ve sahipsiz etkisiz."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from ...core.lesson_runtime import HINT_LIMIT
from ...core.memory import Lesson, LessonMemory, LessonRecallPolicy
from ...core.redaction import redact
from ...memory.lessons import _LESSON_PREAMBLE, _prompt_safe
from ...memory.store import _automatic_read_scope

AUTO_RECALL_TIMEOUT_S = 1.0
AUTO_HINT_TOTAL_CHARS = 4096
_MAX_RAW_CHARS = 8192
_MAX_LESSON_CHARS = 1400
# The permit belongs to the actual worker, never the timed-out/cancelled caller.
# No queue/executor: a stuck native call keeps this one slot until it really returns.
_slot = threading.BoundedSemaphore(1)
_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RecallRequest:
    memory: LessonMemory
    task: str
    root: Path
    tools: tuple[str, ...]
    owner: str
    policy: LessonRecallPolicy


@dataclass(frozen=True, slots=True)
class HintResult:
    block: str = ""
    lessons: tuple[Lesson, ...] = ()


def _format(lessons: tuple[Lesson, ...]) -> HintResult:
    prefix = f"<dersler>\n{_LESSON_PREAMBLE}\n"
    suffix = "\n</dersler>"
    lines: list[str] = []
    delivered: list[Lesson] = []
    for lesson in lessons[:HINT_LIMIT]:
        # Never cut a secret at an arbitrary legacy boundary before redaction.
        if len(lesson.text) > _MAX_RAW_CHARS:
            continue
        text = _prompt_safe(redact(lesson.text)).strip()
        if not text or len(text) > _MAX_LESSON_CHARS:
            continue
        # Provenance is a bounded identifier, not a claim of verified truth.
        identity = hashlib.sha256(lesson.id.encode()).hexdigest()[:12]
        external = "[dış kaynaklı, doğrulanmadı]" if lesson.external else ""
        kind = "KAÇIN" if lesson.kind.value == "mistake" else "UYGULA"
        line = f"- [{kind}]{external} [ders:{identity}] {text}"
        candidate = prefix + "\n".join([*lines, line]) + suffix
        if len(candidate) <= AUTO_HINT_TOTAL_CHARS:
            lines.append(line)
            delivered.append(lesson)
    return (
        HintResult(prefix + "\n".join(lines) + suffix, tuple(delivered)) if lines else HintResult()
    )


def _read(request: RecallRequest) -> HintResult:
    from .learning_steps import _lesson_tags_for

    # Filesystem resolution/marker probes may block too: keep them off the event loop.
    workspace = str(request.root.resolve())
    tags = _lesson_tags_for(request.root, request.tools, request.owner)
    with _automatic_read_scope():
        lessons = request.memory.recall(
            request.task, limit=HINT_LIMIT, workspace=workspace, tags=tags, policy=request.policy
        )
    return _format(lessons)


async def retrieve(request: RecallRequest, *, max_wait_s: float | None = None) -> HintResult:
    """Deadline applies to waiting, not backend termination; late data has no owner effects."""
    wait_s = (
        min(AUTO_RECALL_TIMEOUT_S, max_wait_s) if max_wait_s is not None else AUTO_RECALL_TIMEOUT_S
    )
    if wait_s <= 0 or not _slot.acquire(blocking=False):
        return HintResult()
    event_loop = asyncio.get_running_loop()
    deadline = event_loop.time() + wait_s
    completed: asyncio.Future[HintResult] = event_loop.create_future()

    def deliver(result: HintResult) -> None:
        if not completed.done() and event_loop.time() < deadline:
            completed.set_result(result)

    def worker() -> None:
        try:
            result = _read(request)
        except Exception as error:
            # Optional hints may fail; task/lesson/error strings may contain secrets.
            _logger.debug("Otomatik ders okuması atlandı (%s).", type(error).__name__)
            result = HintResult()
        finally:
            _slot.release()
        try:
            if not event_loop.is_closed():
                event_loop.call_soon_threadsafe(deliver, result)
        except RuntimeError:
            pass  # The owning loop closed between the check and completion handoff.

    try:
        threading.Thread(target=worker, name="fusion-auto-recall", daemon=True).start()
    except Exception:
        _slot.release()
        return HintResult()
    try:
        done, _pending = await asyncio.wait(
            {completed}, timeout=max(0, deadline - event_loop.time())
        )
        return completed.result() if done and event_loop.time() < deadline else HintResult()
    finally:
        # Worker never holds deps, publisher or a callback mutating a session.
        if not completed.done():
            completed.cancel()

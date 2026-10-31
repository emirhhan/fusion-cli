"""Arka plan görevinin işçi süreci: `fusion arka-plan-calistir --dizin <depo> <kimlik>` (P-048).

İşçi görevi `fusion agent` ile AYNI motor yolundan (`run_agent_task`) koşar; fark yalnız
yüzeydedir: olaylar JSON-Lines olarak `olaylar.jsonl`'e, onay/soru istekleri `soru.json`'a
yazılır ve görev "girdi bekliyor" durumuna geçer. Kullanıcı `/tasks answer`, `fusion agents
cevapla` ya da masaüstü panelinden cevap verince tur sürer; süre dolarsa istek "sorulamadı"
sayılır (insan reddi değil; bkz. `engines/agent/denial.py`).

Tur bitince gelen kutusundaki devam mesajları sırayla yeni tur olur; kutu boşsa görev
tamamlanır. `durdur` dosyası görülünce süren tur kesilir ve görev "durduruldu" ile kapanır.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from ..core.background_store import BackgroundTaskStore
from ..core.background_tasks import (
    HEARTBEAT_S,
    BackgroundTask,
    BackgroundTaskError,
    InboxMessage,
    TaskStatus,
    summarize,
)
from ..core.clock import SystemClock
from ..core.redaction import redact
from ..core.tools import ToolContext
from ..core.types import Message
from ..engines.agent.approval import ApprovalAnswer, ApprovalMemory, ApprovalRequest, parse_mode
from ..engines.agent.engine_tools import QuestionOption
from ..ui import background_messages as texts

_LOG = logging.getLogger(__name__)

#: Durdurma isteği ve cevap dosyası yoklama aralığı (saniye).
_POLL_S = 0.5
#: Onay isteğinde gösterilecek argüman özeti uzunluğu.
_ARGS_CHARS = 300
#: Onay kararları (Türkçe kısa yazımlar dahil) → `ApprovalAnswer`.
_DECISIONS: dict[str, ApprovalAnswer] = {
    **dict.fromkeys(("evet", "e", "onayla", "once", "allow", "yes", "y"), ApprovalAnswer.ONCE),
    **dict.fromkeys(("oturum", "session", "hep"), ApprovalAnswer.SESSION),
    **dict.fromkeys(("hayir", "hayır", "h", "reddet", "deny", "no", "n"), ApprovalAnswer.DENY),
}


def parse_decision(raw: str) -> ApprovalAnswer:
    """Kullanıcı cevabını karara çevir; tanınmayan cevap 'sorulamadı' sayılır."""
    return _DECISIONS.get(raw.strip().casefold(), ApprovalAnswer.UNAVAILABLE)


class FileQuestionPrompter:
    """Onay ve soruları görev klasörüne yazıp cevabı bekleyen arayüz (`Prompter` + `UserAsker`)."""

    def __init__(self, store: BackgroundTaskStore, task_id: str, *, timeout_s: float) -> None:
        self._store = store
        self._task_id = task_id
        self._timeout_s = timeout_s
        self._counter = 0

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer:
        args = summarize(redact(str(request.args)), _ARGS_CHARS)
        summary = texts.BG_APPROVAL_SUMMARY.format(tool=request.tool.name, args=args)
        reply = await self._ask(
            {"tur": "onay", "arac": request.tool.name, "ozet": summary, "tehlike": request.danger},
            summary,
        )
        return parse_decision(reply) if reply is not None else ApprovalAnswer.UNAVAILABLE

    async def ask(
        self,
        question: str,
        options: tuple[QuestionOption, ...] = (),
        recommended: str | None = None,
    ) -> str:
        payload: dict[str, object] = {
            "tur": "soru",
            "ozet": summarize(question, _ARGS_CHARS),
            "secenekler": [option.label for option in options],
            "onerilen": recommended or "",
        }
        reply = await self._ask(payload, summarize(question, _ARGS_CHARS))
        return reply or texts.BG_NO_ANSWER

    async def _ask(self, payload: dict[str, object], summary: str) -> str | None:
        self._counter += 1
        request_id = str(self._counter)
        self._store.ask(self._task_id, request_id, payload)
        self._store.update(self._task_id, status=TaskStatus.NEEDS_INPUT, question=summary)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout_s
        try:
            while loop.time() < deadline:
                reply = self._store.take_answer(self._task_id, request_id)
                if reply is not None:
                    return reply
                await asyncio.sleep(_POLL_S)
            return None
        finally:
            self._store.clear_question(self._task_id)
            self._store.update(self._task_id, status=TaskStatus.WORKING, question="")


#: Tek tur çalıştıran işlev: (görev, istem, geçmiş) → (nihai metin, başarı).
TurnRunner = Callable[[BackgroundTask, str, list[Message]], Awaitable[tuple[str, bool]]]


async def run_task_loop(store: BackgroundTaskStore, task_id: str, run_turn: TurnRunner) -> int:
    """Görevin bütün turlarını koştur; çıkış kodu 0 = tamamlandı."""
    task = store.update(task_id, status=TaskStatus.WORKING, pid=os.getpid(), note="")
    store.clear_stop(task_id)
    history = [Message(item["role"], item["content"]) for item in store.load_history(task_id)]
    prompt = task.prompt if task.turns == 0 else _follow_up_text(store.take_inbox(task_id))
    if not prompt:
        # Mesajı başka bir işçi çoktan aldı: yapacak iş yok, kayıt eski hâline döner.
        store.update(task_id, status=TaskStatus.COMPLETED, pid=0)
        return 0
    beat = asyncio.ensure_future(_heartbeat(store, task_id))
    ok = True
    try:
        while prompt:
            outcome = await _turn_or_stop(store, task_id, run_turn(task, prompt, history))
            if outcome is None:
                store.update(task_id, status=TaskStatus.STOPPED, note=texts.BG_STOPPED_NOTE, pid=0)
                return 130
            final_text, ok = outcome
            history = [*history, Message("user", prompt), Message("assistant", final_text)]
            store.save_history(task_id, [{"role": m.role, "content": m.content} for m in history])
            store.write_result(task_id, final_text)
            task = store.update(task_id, turns=task.turns + 1, summary=summarize(final_text))
            task, messages = store.finish_unless_inbox(
                task_id,
                status=TaskStatus.COMPLETED if ok else TaskStatus.FAILED,
                delivered=not task.owner,
                pid=0,
            )
            prompt = _follow_up_text(messages)
    except Exception as error:
        # Sınır: işçi sürecinin tepesi. Ayrıntı günlüğe, kullanıcıya kısa ve sırsız not.
        _LOG.exception("arka plan görevi beklenmeyen hatayla bitti")
        store.update(
            task_id,
            status=TaskStatus.FAILED,
            note=texts.BG_FAILED_NOTE.format(error=type(error).__name__),
            delivered=not task.owner,
            pid=0,
        )
        return 1
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
    return 0 if ok else 1


def _follow_up_text(messages: tuple[InboxMessage, ...]) -> str:
    """Devam mesajlarını tek tura birleştir; başka oturumdan geleni etiketle."""
    parts: list[str] = []
    for message in messages:
        if message.trusted:
            parts.append(message.text)
        else:
            parts.append(
                texts.BG_UNTRUSTED_FOLLOW_UP.format(sender=message.sender, text=message.text)
            )
    return "\n\n".join(parts)


async def _turn_or_stop(
    store: BackgroundTaskStore, task_id: str, turn: Awaitable[tuple[str, bool]]
) -> tuple[str, bool] | None:
    """Turu koştur; durdurma isteği gelirse turu iptal edip None döndür."""
    work = asyncio.ensure_future(turn)
    try:
        while not work.done():
            if store.stop_requested(task_id):
                work.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await work
                return None
            await asyncio.wait({work}, timeout=_POLL_S)
        return work.result()
    finally:
        if not work.done():
            work.cancel()


async def _heartbeat(store: BackgroundTaskStore, task_id: str) -> None:
    while True:
        try:
            store.heartbeat(task_id)
        except OSError:
            _LOG.warning("arka plan nabzı yazılamadı", exc_info=True)
        await asyncio.sleep(HEARTBEAT_S)


def agent_turn_runner(timeout_s: float, store: BackgroundTaskStore) -> TurnRunner:
    """Gerçek motorla tur koşan işlev (`fusion agent` ile aynı yol)."""

    async def _run(task: BackgroundTask, prompt: str, history: list[Message]) -> tuple[str, bool]:
        from ..config.loader import load_config
        from ..observability.usage_log import open_usage_log
        from .headless import resolve_agent
        from .repl.persona_commands import persona_turn
        from .session import build_observers, open_memory, run_agent_task

        config = load_config()
        root = Path(task.root)
        persona = resolve_agent(task.agent, home=Path.home(), root=root) if task.agent else None
        turn = persona_turn(persona)
        observers = build_observers(
            prompt,
            as_json=True,
            trace_dir=config.memory_dir / "traces",
            usage_log=open_usage_log(config),
        )
        try:
            outcome = await run_agent_task(
                prompt,
                config,
                sinks=observers.sinks,
                prompter_factory=lambda _flush: FileQuestionPrompter(
                    store, task.id, timeout_s=timeout_s
                ),
                mode=parse_mode(task.mode),
                root=root,
                home=Path.home(),
                memory=open_memory(config, root=root),
                history=history,
                tool_context=ToolContext(
                    root=root, restrict_to_root=config.runtime.restrict_to_root
                ),
                conversation_id=f"arka-{task.id}",
                extra_system="\n\n".join(
                    p for p in (texts.BG_WORKER_BRIEF, turn.extra_system) if p
                ),
                step_limit=task.max_turns or None,
                allowed_tools=turn.allowed_tools,
                denied_tools=turn.denied_tools
                | (_mutating_tools() if task.read_only else frozenset()),
                interactive=True,
                approval_memory=ApprovalMemory(),
            )
        finally:
            observers.finish()
        return outcome.final_text, bool(outcome.ok) and bool(outcome.final_text.strip())

    return _run


def _mutating_tools() -> frozenset[str]:
    from ..tools.builtin import build_registry

    registry = build_registry()
    return frozenset(
        name for name in registry.names() if (tool := registry.get(name)) and tool.mutating
    )


def main(argv: list[str] | None = None) -> int:
    """İşçi giriş noktası (`python -m` ve gizli `fusion arka-plan-calistir`)."""
    parser = argparse.ArgumentParser(prog="fusion arka-plan-calistir")
    parser.add_argument("--dizin", required=True, type=Path)
    parser.add_argument("kimlik")
    args = parser.parse_args(argv)
    return run_worker(args.dizin, args.kimlik)


def run_worker(store_dir: Path, task_id: str) -> int:
    from ..config.loader import load_config

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    store = BackgroundTaskStore(store_dir, SystemClock())
    try:
        store.get(task_id)
        timeout_s = float(load_config().runtime.background_input_timeout_s)
    except (BackgroundTaskError, OSError) as error:
        _LOG.error("arka plan görevi açılamadı: %s", error)
        return 2
    from .cleanup import with_web_cleanup

    return asyncio.run(
        with_web_cleanup(run_task_loop(store, task_id, agent_turn_runner(timeout_s, store)))
    )


if __name__ == "__main__":
    raise SystemExit(main())

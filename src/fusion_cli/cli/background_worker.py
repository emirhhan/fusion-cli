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
import json
import logging
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path

from ..config.models import Config
from ..core.background_store import BackgroundTaskStore
from ..core.background_tasks import (
    HEARTBEAT_S,
    WORKER_CONVERSATION_PREFIX,
    BackgroundTask,
    BackgroundTaskError,
    InboxMessage,
    TaskStatus,
    approval_word,
    normalize_name,
    summarize,
)
from ..core.clock import SystemClock
from ..core.file_lease import FileLease
from ..core.peers import INBOUND_TAG
from ..core.redaction import redact
from ..core.tools import ToolContext
from ..core.types import Message
from ..core.untrusted_text import neutralize_closing_tags
from ..engines.agent.approval import ApprovalAnswer, ApprovalMemory, ApprovalRequest, parse_mode
from ..engines.agent.engine_tools import QuestionOption
from ..ui import background_messages as texts

_LOG = logging.getLogger(__name__)

#: Durdurma isteği ve cevap dosyası yoklama aralığı (saniye).
_POLL_S = 0.5
#: Onay isteğinde gösterilecek argüman özeti uzunluğu.
_ARGS_CHARS = 300
#: `soru.json`'a konan TAM argüman metninin üst sınırı (redakte; panel/ayrıntıda gösterilir).
_FULL_ARGS_CHARS = 8_000
_DECISIONS: dict[str, ApprovalAnswer] = {
    "once": ApprovalAnswer.ONCE,
    "session": ApprovalAnswer.SESSION,
    "deny": ApprovalAnswer.DENY,
}


def parse_decision(raw: str) -> ApprovalAnswer:
    """Kullanıcı cevabını karara çevir; tanınmayan cevap 'sorulamadı' sayılır."""
    word = approval_word(raw)
    return _DECISIONS[word] if word is not None else ApprovalAnswer.UNAVAILABLE


def _full_args(args: object) -> str:
    try:
        text = json.dumps(args, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        text = str(args)
    return redact(text)


class FileQuestionPrompter:
    """Onay ve soruları görev klasörüne yazıp cevabı bekleyen arayüz (`Prompter` + `UserAsker`)."""

    def __init__(self, store: BackgroundTaskStore, task_id: str, *, timeout_s: float) -> None:
        self._store = store
        self._task_id = task_id
        self._timeout_s = timeout_s
        self._counter = 0

    async def confirm(self, request: ApprovalRequest) -> bool | ApprovalAnswer:
        full = _full_args(request.args)
        flat = " ".join(full.split())
        summary = texts.BG_APPROVAL_SUMMARY.format(
            tool=request.tool.name, args=summarize(flat, _ARGS_CHARS)
        )
        if len(flat) > _ARGS_CHARS:
            # Kırpılan kuyruk onaysız çalışmasın: kullanıcı tam metnin nerede olduğunu bilsin.
            summary += texts.BG_APPROVAL_TRUNCATED.format(
                count=len(flat) - _ARGS_CHARS, id=self._task_id
            )
        reply = await self._ask(
            {
                "tur": "onay",
                "arac": request.tool.name,
                "ozet": summary,
                "arguman": full[:_FULL_ARGS_CHARS],
                "tehlike": request.danger or "",
            },
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


#: Ömür kilidini bekleme süresi (saniye): biten önceki işçi kilidi bırakırken yeni işçi
#: başlayabilir (gelen mesaj bitmiş görevi yeniden başlatır).
_LEASE_WAIT_S = 5.0


async def _acquire_lease(lease: FileLease) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _LEASE_WAIT_S
    while not lease.try_acquire():
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(_POLL_S / 5)
    return True


async def run_task_loop(store: BackgroundTaskStore, task_id: str, run_turn: TurnRunner) -> int:
    """Görevin bütün turlarını koştur; çıkış kodu 0 = tamamlandı.

    İşçi ömür kilidini (`isci.kilit`) alamazsa başka bir işçi canlıdır: hiçbir şeye
    dokunmadan çıkar (aynı kayıtta iki işçi yarışmaz, özgün istem ikinci kez koşmaz).
    """
    lease = store.worker_lease(task_id)
    if not await _acquire_lease(lease):
        _LOG.warning("arka plan görevinin başka bir işçisi çalışıyor; bu işçi çıkıyor")
        return 0
    try:
        return await _run_locked(store, task_id, run_turn)
    finally:
        lease.close()


async def _run_locked(store: BackgroundTaskStore, task_id: str, run_turn: TurnRunner) -> int:
    if store.stop_requested(task_id) or store.get(task_id).status is TaskStatus.STOPPED:
        # Ölçüldü (31 Ekim): sıradayken durdurulan görevin işçisi geç başlayınca kaydı
        # yeniden "çalışıyor" yapıp durdurma isteğini siliyordu.
        return 130
    task = store.update(task_id, status=TaskStatus.WORKING, pid=os.getpid(), note="")
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
                texts.BG_UNTRUSTED_FOLLOW_UP.format(
                    sender=normalize_name(message.sender) or "bilinmeyen",
                    text=neutralize_closing_tags(message.text, INBOUND_TAG),
                )
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


def task_config(task: BackgroundTask, base: Config) -> Config:
    """Yapılandırma + görevin `-c`/`--profile` geçersiz kılmaları + bütçe/`--bare`."""
    from ..config import model_select
    from ..config.settings_access import apply_overrides
    from .headless import apply_limits

    options = task.options
    config = apply_overrides(base, options.config_overrides) if options.config_overrides else base
    if options.profile:
        tier = model_select.normalize_tier_name(options.profile.strip().lower())
        config = model_select.apply_tier(config, tier)
    return apply_limits(
        config, max_turns=None, max_budget_usd=options.max_budget_usd or None, bare=options.bare
    )


def task_tool_limits(
    task: BackgroundTask, allowed: set[str] | None, denied: frozenset[str]
) -> tuple[set[str] | None, frozenset[str]]:
    """Kişiliğin araç kümesini görevin tavanı/yasaklarıyla daralt (asla genişletmez).

    Yazma alanı verilmiş görevde düzenleme araçları dışındaki değiştiriciler (kabuk vb.)
    kapanır: alanı yalnız yol denetimli araçlar koruyabilir (`team_policy` ile aynı kural).
    """
    from ..engines.agent.edit_hooks import EDIT_TOOLS

    options = task.options
    if options.allowed_tools is not None:
        cap = set(options.allowed_tools)
        allowed = cap if allowed is None else set(allowed) & cap
    denied = denied | frozenset(options.denied_tools)
    if task.read_only:
        denied |= _mutating_tools()
    elif options.write_scope:
        denied |= _mutating_tools() - EDIT_TOOLS
    return allowed, denied


def task_tool_context(task: BackgroundTask, config: Config) -> ToolContext:
    """Görevin araç bağlamı: kök-dışı engeller yapılandırmadan, yazma alanı görevden."""
    options = task.options
    return ToolContext(
        root=Path(task.root),
        extra_roots=tuple(Path(item) for item in options.extra_roots),
        restrict_to_root=config.runtime.restrict_to_root,
        block_reads_outside_root=config.runtime.block_reads_outside_root,
        block_writes_outside_root=config.runtime.block_writes_outside_root,
        write_scope=(
            () if task.read_only else tuple(Path(item) for item in options.write_scope) or None
        ),
    )


def agent_turn_runner(timeout_s: float, store: BackgroundTaskStore) -> TurnRunner:
    """Gerçek motorla tur koşan işlev (`fusion agent` ile aynı yol).

    Ölçüldü (31 Ekim): işçi `ToolContext`'i yalnız kök ve `restrict_to_root` ile kuruyordu;
    kök-dışı okuma/yazma engelleri (P-002) ve görevin kısıtları işçide uygulanmıyordu.
    """

    async def _run(task: BackgroundTask, prompt: str, history: list[Message]) -> tuple[str, bool]:
        from ..config.loader import load_config
        from ..observability.usage_log import open_usage_log
        from .headless import resolve_agent
        from .repl.persona_commands import persona_turn
        from .session import build_observers, open_memory, run_agent_task

        config = task_config(task, load_config())
        root = Path(task.root)
        persona = resolve_agent(task.agent, home=Path.home(), root=root) if task.agent else None
        turn = persona_turn(persona)
        allowed, denied = task_tool_limits(task, turn.allowed_tools, turn.denied_tools)
        tool_context = task_tool_context(task, config)
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
                memory=open_memory(
                    config, root=root, enabled=task.options.memory and not task.options.bare
                ),
                extra_roots=tool_context.extra_roots,
                history=history,
                tool_context=tool_context,
                conversation_id=f"{WORKER_CONVERSATION_PREFIX}{task.id}",
                extra_system="\n\n".join(
                    p
                    for p in (texts.BG_WORKER_BRIEF, turn.extra_system, task.options.extra_system)
                    if p
                ),
                step_limit=task.max_turns or None,
                allowed_tools=allowed,
                denied_tools=denied,
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

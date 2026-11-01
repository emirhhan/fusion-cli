"""Ajan döngüsü ↔ kanca sistemi (P-009): loop.py yalnız bu işlevleri çağırır.

    PreToolUse          onaydan ÖNCE: engel (çıkış 2 / deny), `updatedInput` (girdinin
                        TAMAMI), izin kararı allow|ask → bu çağrıya özel izin kuralı (deny ve
                        ask kurallarını, yıkıcı komut onayını ve plan kipini GEÇEMEZ),
                        `defer` (`-p`'de turu bitirir), `additionalContext` araç sonucuna
    PostToolUse(+Failure) araç sonrası: engel/bağlam modele araç sonucunun yanında gider
    UserPromptSubmit    kök tur başında: engel istemi düşürür, bağlam istemin yanına eklenir
    Stop / SubagentStop tur sonunda (`hook_stop.py`)
    PreCompact          bağlam özetlenmeden önce; çıkış 2 / `decision: block` özetlemeyi atlar
    PostCompact         özetlemeden sonra (`compact_summary`)

Eşleştirici yalnız `tool_name`'e (birincil Claude adı ya da `mcp__sunucu__araç`) uygulanır;
aile genişlemesi (`Edit` → bütün yazma araçları) yalnız izin kurallarındadır.
`deps.hooks` yoksa (alt sistem testleri, eski çağıranlar) her işlev hiçbir şey yapmaz.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from ...config.permission_rules import PermissionDecision, PermissionRule, PermissionRuleSet
from ...core.events import Channel, ErrorOccurred, EventPublisher, NarrationPublished
from ...core.hooks.events import HookEvent, HookVerdict
from ...core.tools import ToolResult
from ...core.types import Message
from ...tools.permission_match import claude_tool_names
from ...ui import messages
from ..hooks.session import HookSession
from . import hook_text
from .hook_input import claude_tool_input, claude_tool_response, fusion_tool_args
from .skill_hooks import after_skill_tool

if TYPE_CHECKING:
    from .loop import AgentDeps

#: Araç çıktısından kancaya gönderilen en fazla karakter.
HOOK_TOOL_OUTPUT_CHARS = 20_000
#: Hook kararıyla eklenen izin kuralının kaynak adı (onay kartında görünür).
HOOK_RULE_SOURCE = "kanca"
#: Kanca durdurmasının araç sonucundaki işareti (`structured` alanı).
HOOK_HALT_KEY = "hook_halt"
#: `defer` kararının araç sonucundaki işareti (Claude `-p`: `tool_deferred`).
TOOL_DEFERRED = "tool_deferred"
_MCP_PREFIX = "mcp__"


def session_of(deps: AgentDeps) -> HookSession | None:
    return getattr(deps, "hooks", None)


def records_tools(deps: AgentDeps) -> bool:
    """Ana ajan mı? Döküm ve oturum olayları yalnız onun (Claude'da alt ajan ayrıdır)."""
    return getattr(deps, "channel", None) is not Channel.SUBAGENT


def hook_halt_text(result: ToolResult) -> str | None:
    """PreToolUse `continue: false` ile engellenen sonucun kullanıcı metni; değilse `None`."""
    marker = (result.structured or {}).get(HOOK_HALT_KEY)
    return marker if isinstance(marker, str) else None


@dataclass(frozen=True, slots=True)
class ToolGate:
    """PreToolUse sonucu: çalıştırılacak argümanlar ya da engel."""

    arguments: dict[str, object]
    blocked: str | None = None
    #: `continue: false` (ya da `-p`'de `defer`) — tur durur (çağrı reddedilmiş gibi).
    halt: bool = False
    permission: str | None = None
    #: `ask` gerekçesi: onay kartında kuralın kaynağıyla görünür.
    ask_reason: str = ""

    def failure(self) -> ToolResult:
        """Engellenen çağrının sonucu; `continue: false` ise durdurma işaretli."""
        marker = {HOOK_HALT_KEY: self.blocked} if self.halt else None
        return ToolResult.failure(self.blocked or "", structured=marker)

    def rules(self, current: PermissionRuleSet | None, tool_name: str) -> PermissionRuleSet | None:
        """Kancanın allow/ask kararı bu çağrıya özel kural olur (en kısıtlayıcı kazanır)."""
        if self.permission not in ("allow", "ask"):
            return current
        source = f"{HOOK_RULE_SOURCE}: {self.ask_reason}" if self.ask_reason else HOOK_RULE_SOURCE
        # Belirteçsiz kural aracın bütün çağrılarına uyar (kabuk zinciri dahil).
        rule = PermissionRule(tool_name, None, PermissionDecision(self.permission), source)
        base = current if current is not None else PermissionRuleSet()
        return base.with_rules((*base.rules, rule))


def _root(session: HookSession) -> Path:
    return session.root


async def pre_tool_use(
    deps: AgentDeps, tool_name: str, args: dict[str, object], call_id: str = ""
) -> ToolGate:
    session = session_of(deps)
    if session is None:
        return ToolGate(args)
    fields = tool_hook_fields(tool_name, args, call_id, root=_root(session), deps=deps)
    claude_name = str(fields["tool_name"])
    if records_tools(deps):
        tool_input = fields["tool_input"]
        session.record_tool_use(
            claude_name, tool_input if isinstance(tool_input, dict) else args, call_id
        )
    verdict = await session.emit(
        HookEvent.PRE_TOOL_USE, subjects=(claude_name,), fields=fields, target=(tool_name, args)
    )
    _publish(deps, verdict)
    gate = _blocking_gate(deps, args, claude_name, verdict)
    if gate is not None:
        if records_tools(deps):
            session.record_tool_result(call_id, gate.blocked or "", is_error=True)
        return gate
    if verdict.context_text:
        session.pending_tool_context[call_id] = hook_text.context_reminder(
            HookEvent.PRE_TOOL_USE, verdict.context_text
        )
    arguments = (
        fusion_tool_args(tool_name, args, verdict.updated_input, _root(session))
        if verdict.updated_input is not None
        else args
    )
    tool_running(deps, tool_name, arguments, call_id)
    return ToolGate(arguments, permission=verdict.permission, ask_reason=verdict.ask_reason)


def _blocking_gate(
    deps: AgentDeps, args: dict[str, object], subject: str, verdict: HookVerdict
) -> ToolGate | None:
    event = HookEvent.PRE_TOOL_USE
    if verdict.halt:
        reason = verdict.stop_reason or verdict.reason or messages.HOOKS_NO_REASON
        return ToolGate(
            args, messages.HOOKS_TURN_HALTED.format(event=event.value, reason=reason), True
        )
    if verdict.blocked:
        return ToolGate(args, hook_text.block_error(event, subject, verdict))
    if verdict.permission == "defer" and not getattr(deps, "interactive", False):
        return ToolGate(args, TOOL_DEFERRED, True)
    return None


def tool_running(
    deps: AgentDeps, tool_name: str, args: Mapping[str, object], call_id: str = ""
) -> None:
    """Araç ŞİMDİ çalışıyor (onaydan sonra): `duration_ms` başlangıcı ve Write `type`.

    PreToolUse da çağırır (onaysız yollar için); döngü onaydan sonra yeniden çağırır ki
    Claude'daki gibi süre onay beklemesini içermesin.
    """
    session = session_of(deps)
    if session is None:
        return
    session.tool_started[call_id] = time.monotonic()
    _share_env_file(deps, session)
    if tool_name == "write_file":
        shape = claude_tool_input(tool_name, args, _root(session))
        path = shape.get("file_path")
        if isinstance(path, str):
            session.tool_existed[call_id] = Path(path).exists()


def _share_env_file(deps: AgentDeps, session: HookSession) -> None:
    """Oturumun `CLAUDE_ENV_FILE`'ı kabuk aracına (alt ajan ana oturumunkini paylaşır)."""
    shared = getattr(getattr(deps, "tool_context", None), "shell_env_files", None)
    if shared is None or not records_tools(deps):
        return
    env_file = session.env_file()
    shared[:] = [env_file] if env_file is not None else []


@dataclass(frozen=True, slots=True)
class ToolNote:
    """PostToolUse sonucu: modele eklenecek not, çıktı değişimi, tur durdurma."""

    note: str | None = None
    replaced_output: str | None = None
    #: `continue: false`: turu durduran kullanıcı metni (`None` = sürer).
    halt: str | None = None


async def post_tool_use(
    deps: AgentDeps,
    tool_name: str,
    args: Mapping[str, object],
    output: str,
    *,
    ok: bool,
    call_id: str = "",
) -> ToolNote:
    session = session_of(deps)
    if session is None:
        return ToolNote()
    event = HookEvent.POST_TOOL_USE if ok else HookEvent.POST_TOOL_USE_FAILURE
    fields = tool_hook_fields(tool_name, args, call_id, root=_root(session), deps=deps)
    clipped = output[:HOOK_TOOL_OUTPUT_CHARS]
    if records_tools(deps):
        session.record_tool_result(call_id, clipped, is_error=not ok)
    started = session.tool_started.pop(call_id, None)
    if started is not None:
        fields["duration_ms"] = int((time.monotonic() - started) * 1000)
    tool_input = fields["tool_input"]
    if ok:
        shape = tool_input if isinstance(tool_input, Mapping) else {}
        existed = session.tool_existed.pop(call_id, None)
        fields["tool_response"] = claude_tool_response(tool_name, shape, clipped, existed=existed)
    else:
        session.tool_existed.pop(call_id, None)
        fields["error"] = clipped
        fields["is_interrupt"] = False
    claude_name = str(fields["tool_name"])
    verdict = await session.emit(
        event, subjects=(claude_name,), fields=fields, target=(tool_name, args)
    )
    _publish(deps, verdict)
    after_skill_tool(deps, session, tool_name, args, ok=ok)
    notes = [session.pending_tool_context.pop(call_id, "")]
    if verdict.blocked:
        notes.append(hook_text.block_error(event, claude_name, verdict))
    notes.append(hook_text.context_reminder(event, verdict.context_text))
    halt: str | None = None
    if verdict.halt:
        reason = verdict.stop_reason or messages.HOOKS_NO_REASON
        halt = messages.HOOKS_TURN_HALTED.format(event=event.value, reason=reason)
        notes.append(halt)
    note = "\n\n".join(part for part in notes if part)
    return ToolNote(note or None, verdict.updated_output, halt)


@dataclass(frozen=True, slots=True)
class PromptGate:
    """Kök tur başı: istem engellendiyse mesaj; değilse istemin önüne/yanına eklenecek bağlam."""

    blocked: str | None = None
    #: SessionStart bağlamı (konuşmanın başında, istemden önce).
    before: str = ""
    #: UserPromptSubmit bağlamı (istemin yanında).
    after: str = ""

    @property
    def context(self) -> str:
        return "\n\n".join(part for part in (self.before, self.after) if part)

    def model_prompt(self, task: str) -> str:
        """Modele giden kullanıcı mesajı: bağlam geçmişte istemle birlikte kalıcı kalır."""
        return "\n\n".join(part for part in (self.before, task, self.after) if part)


async def user_prompt_submit(deps: AgentDeps, prompt: str) -> PromptGate:
    """SessionStart (açılmadıysa) + UserPromptSubmit; tanımlar her kök turda tazelenir."""
    session = session_of(deps)
    if session is None:
        return PromptGate()
    session.refresh()
    notice = session.disabled_notice()
    if notice is not None:
        deps.publisher.publish(
            NarrationPublished(text=messages.HOOKS_DISABLED_NOTICE.format(reason=notice))
        )
    for text in session.take_notices():
        deps.publisher.publish(NarrationPublished(text=messages.HOOKS_SYSTEM.format(text=text)))
    started = await session.start()
    _publish(deps, started)
    session.new_prompt()
    from .hook_expansion import prompt_expansion

    expansion = await prompt_expansion(session)
    if expansion.verdict is not None:
        _publish(deps, expansion.verdict)
    if expansion.blocked is not None:
        return PromptGate(blocked=expansion.blocked)
    verdict = await session.emit(HookEvent.USER_PROMPT_SUBMIT, fields={"prompt": prompt})
    _publish(deps, verdict)
    if verdict.session_title or started.session_title:
        session.session_title = verdict.session_title or started.session_title
    if verdict.blocked or verdict.halt:
        reason = verdict.reason or verdict.stop_reason or messages.HOOKS_NO_REASON
        text = hook_text.prompt_blocked(reason, prompt, suppress=verdict.suppress_original_prompt)
        return PromptGate(blocked=text)
    session.record("user", prompt)
    before = session.take_start_context() or hook_text.context_reminder(
        HookEvent.SESSION_START, started.context_text
    )
    rewake = [hook_text.system_reminder(note) for note in session.take_rewake_notes()]
    after = "\n\n".join(
        part
        for part in (
            hook_text.context_reminder(HookEvent.USER_PROMPT_EXPANSION, expansion.context),
            hook_text.context_reminder(HookEvent.USER_PROMPT_SUBMIT, verdict.context_text),
            *rewake,
        )
        if part
    )
    return PromptGate(before=before, after=after)


async def pre_compact(deps: AgentDeps, trigger: str, instructions: str | None = None) -> bool:
    """`PreCompact`; kanca engellediyse `True` (özetleme atlanır)."""
    session = session_of(deps)
    if session is None:
        return False
    verdict = await session.pre_compact(trigger, instructions)
    _publish(deps, verdict)
    return verdict.blocked


async def compacted_context(deps: AgentDeps, trigger: str = "auto", summary: str = "") -> str:
    """Özetleme sonrası `PostCompact` + `SessionStart(compact)`; modele bağlam notu (yoksa boş).

    Yalnız ana ajanda: alt ajanın bağlam özeti oturum olayı değildir. Ölçüldü (1 Kasım):
    özetlemeden sonra SessionStart hiç tetiklenmiyordu; açılışta bağlam ekleyen betiklerin
    notu özetle birlikte kayboluyordu (Claude `compact` kaynağıyla yeniden ekletir).
    """
    session = session_of(deps)
    if session is None or not records_tools(deps):
        return ""
    _publish(deps, await session.post_compact(trigger, summary))
    verdict = await session.compacted()
    _publish(deps, verdict)
    return hook_text.context_reminder(HookEvent.SESSION_START, verdict.context_text)


def with_system_note(conversation: list[Message], note: str) -> list[Message]:
    """Notu sistem mesajının sonuna ekle (rol sırası bozulmasın); sistem yoksa başa koy."""
    if not note:
        return conversation
    if conversation and conversation[0].role == "system":
        first = conversation[0]
        return [replace(first, content=f"{first.content}\n\n{note}"), *conversation[1:]]
    return [Message("system", note), *conversation]


def _publish(deps: AgentDeps, verdict: HookVerdict) -> None:
    publish_verdict(deps.publisher, verdict)


def publish_verdict(publisher: EventPublisher, verdict: HookVerdict) -> None:
    """`systemMessage` ve engellemeyen hatalar kullanıcıya; model görmez."""
    for text in verdict.system_messages:
        publisher.publish(NarrationPublished(text=messages.HOOKS_SYSTEM.format(text=text)))
    for detail in verdict.errors:
        publisher.publish(ErrorOccurred(messages.HOOKS_ERROR.format(detail=detail)))


def mcp_server_field(server: str, deps: AgentDeps | None) -> dict[str, object]:
    """Claude `mcp_server`: `name` ve tanımın geldiği yer (`source`: user|project|plugin)."""
    field: dict[str, object] = {"name": server}
    config = getattr(deps, "config", None) if deps is not None else None
    for entry in getattr(config, "mcp_servers", ()) or ():
        if getattr(entry, "name", None) == server:
            scope = getattr(entry, "scope", None)
            field["source"] = str(getattr(scope, "value", scope) or "user")
            break
    return field


def tool_hook_fields(
    tool_name: str,
    args: Mapping[str, object],
    call_id: str = "",
    *,
    root: Path | None = None,
    deps: AgentDeps | None = None,
) -> dict[str, object]:
    """Claude yükü: `tool_name` birincil Claude adı, `tool_input` Claude aracının şekli.

    `tool_use_id` PreToolUse ile PostToolUse'u eşler (çağrı kimliği; yoksa alan yazılmaz).
    MCP aracında `mcp_server` (sunucu adı); alt ajanda `agent_id`/`agent_type`.
    """
    name = claude_tool_names(tool_name)[0]
    fields: dict[str, object] = {
        "tool_name": name,
        "tool_input": claude_tool_input(tool_name, args, root or Path.cwd()),
    }
    if call_id:
        fields["tool_use_id"] = call_id
    if name.startswith(_MCP_PREFIX):
        server = name[len(_MCP_PREFIX) :].split("__", 1)[0]
        fields["mcp_server"] = mcp_server_field(server, deps)
    if deps is not None and not records_tools(deps):
        fields["agent_id"] = str(getattr(deps, "runtime_agent_id", "") or "")
        fields["agent_type"] = str(getattr(deps, "agent_type", "") or "")
    return fields

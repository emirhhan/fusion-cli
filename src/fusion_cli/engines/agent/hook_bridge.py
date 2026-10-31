"""Ajan döngüsü ↔ kanca sistemi (P-009): loop.py yalnız bu işlevleri çağırır.

    PreToolUse          onaydan ÖNCE: engel (çıkış 2 / deny), `updatedInput`, izin
                        kararı allow|ask → bu çağrıya özel izin kuralı (deny ve ask
                        kurallarını, yıkıcı komut onayını ve plan kipini GEÇEMEZ)
    PostToolUse(+Failure) araç sonrası: engel/bağlam modele not olarak eklenir
    UserPromptSubmit    kök tur başında: engel istemi düşürür, bağlam tura eklenir
    Stop / SubagentStop tur sonunda: engel (`decision: block`) ajanı gerekçeyle sürdürür;
                        en çok `MAX_STOP_CONTINUATIONS` kez, `stop_hook_active` ile
    PreCompact          bağlam özetlenmeden önce (gözlem)

`deps.hooks` yoksa (alt sistem testleri, eski çağıranlar) her işlev hiçbir şey yapmaz.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar

from ...config.permission_rules import PermissionDecision, PermissionRule, PermissionRuleSet
from ...core.events import ErrorOccurred, NarrationPublished
from ...core.hooks.events import HookEvent, HookVerdict
from ...core.tools import ToolResult
from ...core.types import Message
from ...tools.permission_match import claude_tool_names
from ...ui import messages
from ..hooks.session import HookSession

if TYPE_CHECKING:
    from .loop import AgentDeps

#: Stop kancası bir kök turu en çok kaç kez sürdürebilir (Claude'da sınır yok; betik
#: `stop_hook_active` alanına bakmazsa sonsuz döngü olurdu).
MAX_STOP_CONTINUATIONS = 3
#: Araç çıktısından kancaya gönderilen en fazla karakter.
HOOK_TOOL_OUTPUT_CHARS = 20_000
#: Hook kararıyla eklenen izin kuralının kaynak adı (onay kartında görünür).
HOOK_RULE_SOURCE = "kanca"
#: Kanca durdurmasının araç sonucundaki işareti (`structured` alanı).
HOOK_HALT_KEY = "hook_halt"
#: Claude betiklerinin beklediği dosya argümanı adı ↔ Fusion'ınki.
_CLAUDE_PATH_KEY = "file_path"
_FUSION_PATH_KEY = "path"


def session_of(deps: AgentDeps) -> HookSession | None:
    return getattr(deps, "hooks", None)


def hook_halt_text(result: ToolResult) -> str | None:
    """PreToolUse `continue: false` ile engellenen sonucun kullanıcı metni; değilse `None`."""
    marker = (result.structured or {}).get(HOOK_HALT_KEY)
    return marker if isinstance(marker, str) else None


@dataclass(frozen=True, slots=True)
class ToolGate:
    """PreToolUse sonucu: çalıştırılacak argümanlar ya da engel."""

    arguments: dict[str, object]
    blocked: str | None = None
    #: `continue: false` — tur durur (çağrı reddedilmiş gibi).
    halt: bool = False
    permission: str | None = None

    def failure(self) -> ToolResult:
        """Engellenen çağrının sonucu; `continue: false` ise durdurma işaretli."""
        marker = {HOOK_HALT_KEY: self.blocked} if self.halt else None
        return ToolResult.failure(self.blocked or "", structured=marker)

    def rules(self, current: PermissionRuleSet | None, tool_name: str) -> PermissionRuleSet | None:
        """Kancanın allow/ask kararı bu çağrıya özel kural olur (en kısıtlayıcı kazanır)."""
        if self.permission is None:
            return current
        # Belirteçsiz kural aracın bütün çağrılarına uyar (kabuk zinciri dahil).
        rule = PermissionRule(
            tool_name, None, PermissionDecision(self.permission), HOOK_RULE_SOURCE
        )
        base = current if current is not None else PermissionRuleSet()
        return base.with_rules((*base.rules, rule))


async def pre_tool_use(
    deps: AgentDeps, tool_name: str, args: dict[str, object], call_id: str = ""
) -> ToolGate:
    session = session_of(deps)
    if session is None:
        return ToolGate(args)
    verdict = await session.emit(
        HookEvent.PRE_TOOL_USE,
        subjects=claude_tool_names(tool_name),
        fields=tool_hook_fields(tool_name, args, call_id),
    )
    _publish(deps, verdict)
    event = HookEvent.PRE_TOOL_USE.value
    if verdict.halt:
        reason = verdict.stop_reason or verdict.reason or messages.HOOKS_NO_REASON
        return ToolGate(args, messages.HOOKS_TURN_HALTED.format(event=event, reason=reason), True)
    if verdict.blocked:
        return ToolGate(
            args, messages.HOOKS_TOOL_BLOCKED.format(event=event, reason=verdict.reason)
        )
    arguments = _from_claude_input(args, verdict.updated_input)
    return ToolGate(arguments, permission=verdict.permission)


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
    fields = dict(tool_hook_fields(tool_name, args, call_id))
    clipped = output[:HOOK_TOOL_OUTPUT_CHARS]
    if ok:
        fields["tool_response"] = {"output": clipped, "success": True}
    else:
        fields["error"] = clipped
    verdict = await session.emit(event, subjects=claude_tool_names(tool_name), fields=fields)
    _publish(deps, verdict)
    notes: list[str] = []
    if verdict.blocked:
        notes.append(messages.HOOKS_POST_FEEDBACK.format(event=event.value, reason=verdict.reason))
    if verdict.context_text:
        notes.append(
            messages.HOOKS_CONTEXT_NOTE.format(event=event.value, context=verdict.context_text)
        )
    halt: str | None = None
    if verdict.halt:
        reason = verdict.stop_reason or messages.HOOKS_NO_REASON
        halt = messages.HOOKS_TURN_HALTED.format(event=event.value, reason=reason)
        notes.append(halt)
    return ToolNote("\n\n".join(notes) or None, verdict.updated_output, halt)


@dataclass(frozen=True, slots=True)
class PromptGate:
    """Kök tur başı: istem engellendiyse gerekçe; değilse sisteme eklenecek bağlam."""

    blocked: str | None = None
    context: str = ""


async def user_prompt_submit(deps: AgentDeps, prompt: str) -> PromptGate:
    """SessionStart (ilk turda) + UserPromptSubmit; tanımlar her kök turda tazelenir."""
    session = session_of(deps)
    if session is None:
        return PromptGate()
    session.refresh()
    notice = session.disabled_notice()
    if notice is not None:
        deps.publisher.publish(
            NarrationPublished(text=messages.HOOKS_DISABLED_NOTICE.format(reason=notice))
        )
    started = await session.start()
    _publish(deps, started)
    verdict = await session.emit(HookEvent.USER_PROMPT_SUBMIT, fields={"prompt": prompt})
    _publish(deps, verdict)
    if verdict.blocked or verdict.halt:
        reason = verdict.reason or verdict.stop_reason or messages.HOOKS_NO_REASON
        return PromptGate(blocked=messages.HOOKS_PROMPT_BLOCKED.format(reason=reason))
    session.record("user", prompt)
    parts = [
        messages.HOOKS_CONTEXT_NOTE.format(event=item_event.value, context=item.context_text)
        for item_event, item in (
            (HookEvent.SESSION_START, started),
            (HookEvent.USER_PROMPT_SUBMIT, verdict),
        )
        if item.context_text
    ]
    return PromptGate(context="\n\n".join(parts))


async def stop_continuation(
    deps: AgentDeps, final_text: str, *, subagent: bool, continuations: int
) -> str | None:
    """Stop/SubagentStop engellediyse ajanın sürdüreceği istem; durabilirse `None`."""
    session = session_of(deps)
    if session is None:
        return None
    event = HookEvent.SUBAGENT_STOP if subagent else HookEvent.STOP
    agent_type = str(getattr(deps, "agent_type", "") or "")
    fields: dict[str, object] = {
        "stop_hook_active": continuations > 0,
        "last_assistant_message": final_text[:HOOK_TOOL_OUTPUT_CHARS],
    }
    if subagent:
        fields["agent_type"] = agent_type
    else:
        session.record("assistant", final_text)
    verdict = await session.emit(event, subjects=(agent_type,), fields=fields)
    _publish(deps, verdict)
    if verdict.halt or not verdict.blocked:
        return None
    return messages.HOOKS_STOP_CONTINUE.format(event=event.value, reason=verdict.reason)


class _Transcript(Protocol):
    final_text: str
    messages: list[Message]
    ok: bool
    budget_stopped: bool


OutcomeT = TypeVar("OutcomeT", bound=_Transcript)


async def continue_until_stop_allowed(
    deps: AgentDeps,
    outcome: OutcomeT,
    rerun: Callable[[str, list[Message]], Awaitable[OutcomeT]],
    *,
    subagent: bool,
) -> OutcomeT:
    """Stop kancası izin verene (ya da sınır dolana) kadar turu gerekçeyle sürdür.

    Yalnız temiz biten turda sorulur: bütçe/adım sınırı, model hatası, kullanıcı reddi ve
    kanca `continue: false` durdurmasında Stop tetiklenmez (Claude da kesintide ve sınır
    hatasında çalıştırmaz). Ölçüldü (31 Ekim): `agent_max_steps: 1` ile kesilen turda Stop
    kancası 3 kez çağrılıp aynı durdurulmuş bütçeyle ajanı yeniden başlatıyordu.
    """
    for continuation in range(MAX_STOP_CONTINUATIONS):
        if not _ended_cleanly(deps, outcome):
            return outcome
        prompt = await stop_continuation(
            deps, outcome.final_text, subagent=subagent, continuations=continuation
        )
        if prompt is None:
            return outcome
        outcome = await rerun(prompt, outcome.messages)
    return outcome


def _ended_cleanly(deps: AgentDeps, outcome: _Transcript) -> bool:
    budget = getattr(deps, "budget", None)
    stopped = budget is not None and budget.stop is not None
    return outcome.ok and not outcome.budget_stopped and not stopped


async def pre_compact(deps: AgentDeps, trigger: str) -> None:
    session = session_of(deps)
    if session is None:
        return
    _publish(deps, await session.pre_compact(trigger))


def _publish(deps: AgentDeps, verdict: HookVerdict) -> None:
    """`systemMessage` ve engellemeyen hatalar kullanıcıya; model görmez."""
    for text in verdict.system_messages:
        deps.publisher.publish(NarrationPublished(text=messages.HOOKS_SYSTEM.format(text=text)))
    for detail in verdict.errors:
        deps.publisher.publish(ErrorOccurred(messages.HOOKS_ERROR.format(detail=detail)))


def tool_hook_fields(
    tool_name: str, args: Mapping[str, object], call_id: str = ""
) -> dict[str, object]:
    """Claude yükü: `tool_name` birincil Claude adı, `tool_input` + `file_path` takma adı.

    `tool_use_id` PreToolUse ile PostToolUse'u eşler (çağrı kimliği; yoksa alan yazılmaz).
    """
    tool_input = dict(args)
    path = args.get(_FUSION_PATH_KEY)
    if isinstance(path, str) and _CLAUDE_PATH_KEY not in tool_input:
        tool_input[_CLAUDE_PATH_KEY] = path
    fields: dict[str, object] = {
        "tool_name": claude_tool_names(tool_name)[0],
        "fusion_tool_name": tool_name,
        "tool_input": tool_input,
    }
    if call_id:
        fields["tool_use_id"] = call_id
    return fields


def _from_claude_input(
    original: dict[str, object], updated: Mapping[str, object] | None
) -> dict[str, object]:
    """`updatedInput`'u Fusion argümanına çevir: eklediğimiz `file_path` geri `path` olur.

    Alanlar özgün argümanın ÜSTÜNE yazılır: yalnız `{"command": …}` döndüren betik de
    çalışır (verilmeyen alan düşmez).
    """
    if updated is None:
        return original
    arguments = {**original, **updated}
    if _FUSION_PATH_KEY in original and _CLAUDE_PATH_KEY not in original:
        claude_path = arguments.pop(_CLAUDE_PATH_KEY, None)
        if isinstance(claude_path, str) and claude_path != original[_FUSION_PATH_KEY]:
            arguments[_FUSION_PATH_KEY] = claude_path
    return arguments

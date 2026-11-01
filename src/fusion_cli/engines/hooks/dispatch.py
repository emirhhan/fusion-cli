"""Tek kanca komutunun çalıştırılma kuralları (Claude Code hooks başvurusu).

if          izin kuralı sözdizimi; yalnız araç olaylarında değerlendirilir, öteki
            olaylarda `if` taşıyan kanca HİÇ çalışmaz
timeout     yazılmadıysa: UserPromptSubmit 30 sn (command/http/mcp_tool; prompt 30,
            agent 60 sn kalır); SessionEnd ortak 1,5 sn bütçe
onFailure   `block`: başarısızlık (başlatılamadı, ≠0/2, zaman aşımı, şema hatası) çıkış
            2 gibi engeller; Stop/SubagentStop/TaskCompleted/TeammateIdle ve arka plan
            kancalarında etkisizdir
async       arka planda çalışır, kararı beklenmez; `asyncRewake` çıkış 2'de stderr'i
            (boşsa stdout'u) bir sonraki tura sistem hatırlatması olarak bırakır
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from ...config.hooks import explicit_sessionend_timeout_s, sessionend_budget_s
from ...config.permission_rules import PermissionDecision, parse_rule
from ...core.hooks.decision import BLOCK_EXIT_CODE, is_failure, verdict_from_run
from ...core.hooks.events import MODEL_HANDLERS, HookCommand, HookEvent, HookRun, HookVerdict
from ...tools.permission_match import matches

#: `if` alanının değerlendirildiği araç olayları.
TOOL_EVENTS = frozenset(
    {HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE, HookEvent.POST_TOOL_USE_FAILURE}
)
#: Yazılmamış zaman aşımının olay başına Claude varsayılanı (sn).
_EVENT_DEFAULT_TIMEOUT = {HookEvent.USER_PROMPT_SUBMIT: 30.0, HookEvent.PRE_MODEL_SWITCH: 30.0}
#: `onFailure: block`'un etkisiz olduğu olaylar (çıkış 2 ajanı sürdürür).
_NO_FAILURE_BLOCK = frozenset(
    {
        HookEvent.STOP,
        HookEvent.SUBAGENT_STOP,
        HookEvent.TASK_COMPLETED,
        HookEvent.TEAMMATE_IDLE,
    }
)


def condition_allows(
    command: HookCommand,
    event: HookEvent,
    target: tuple[str, Mapping[str, object]] | None,
    root: Path,
) -> bool:
    """`if` koşulu bu çağrıya uyuyor mu? Koşulsuz kanca her zaman çalışır."""
    if not command.condition:
        return True
    if event not in TOOL_EVENTS or target is None:
        return False
    rule = parse_rule(command.condition, PermissionDecision.ALLOW)
    if rule is None:
        return False
    tool_name, arguments = target
    return matches(rule, tool_name, arguments, root)


def with_event_timeout(
    commands: tuple[HookCommand, ...], event: HookEvent
) -> tuple[HookCommand, ...]:
    """Süresi yazılmamış komutlara olayın varsayılanını uygula (SessionEnd ortak bütçe)."""
    if event is HookEvent.SESSION_END:
        longest = max((c.timeout_s for c in commands if c.timeout_explicit), default=0.0)
        budget = sessionend_budget_s(longest)
        fallback = explicit_sessionend_timeout_s() or budget
        return tuple(
            replace(c, timeout_s=min(c.timeout_s if c.timeout_explicit else fallback, budget))
            for c in commands
        )
    default = _EVENT_DEFAULT_TIMEOUT.get(event)
    if default is None:
        return commands
    return tuple(
        c if c.timeout_explicit or c.handler in MODEL_HANDLERS else replace(c, timeout_s=default)
        for c in commands
    )


def apply_on_failure(event: HookEvent, run: HookRun, verdict: HookVerdict) -> HookVerdict:
    """`onFailure: block`: başarısız kanca çıkış 2 gibi engeller (izinli olaylarda).

    Komut kancasında 0/2 dışı çıkış, izin veren JSON yazdırsa da başarısızlıktır.
    """
    command = run.command
    if command.on_failure != "block" or event in _NO_FAILURE_BLOCK or is_background(command):
        return verdict
    odd_exit = command.handler == "command" and run.exit_code not in (0, BLOCK_EXIT_CODE, None)
    if not (is_failure(verdict) or odd_exit):
        return verdict
    if not verdict.errors:
        verdict = replace(
            verdict, errors=(f"{event.value} hook error: çıkış kodu {run.exit_code}",)
        )
    return replace(verdict, blocked=True, reason="\n".join(verdict.errors), permission=None)


def is_background(command: HookCommand) -> bool:
    return command.run_async or command.async_rewake


def async_context(event: HookEvent, run: HookRun) -> str | None:
    """`async` kanca JSON'undaki `systemMessage`/`additionalContext` sonraki tura (Claude)."""
    if run.command.async_rewake:
        return None
    verdict = verdict_from_run(event, run)
    parts = (*verdict.system_messages, *verdict.additional_context)
    return "\n\n".join(part for part in parts if part) or None


def rewake_text(run: HookRun) -> str | None:
    """`asyncRewake` kancası çıkış 2 ile bittiyse modele bırakılacak metin."""
    if not run.command.async_rewake or run.exit_code != BLOCK_EXIT_CODE:
        return None
    return run.stderr.strip() or run.stdout.strip() or None

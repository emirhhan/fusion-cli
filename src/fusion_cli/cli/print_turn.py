"""`-p` turunun istem hazırlığı: yerleşik komut, `/beceri` genişletmesi, araç daraltması.

Tek atışlık `-p` ile `--input-format stream-json`'un her kullanıcı satırı AYNI yoldan geçer
(bağımsız inceleme bulgu 4): önce değer alan yerleşik komutlar (`/model`, `/config` …) modele
gitmeden cevaplanır, sonra beceri/özel komut genişletilir; genişletmenin `allowed-tools`
daraltması ve ek sistem metni YALNIZ o tura uygulanır (`run.slash` her turda yenilenir).
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..tools.capabilities import CapabilityRegistry
from ..tools.capability_overrides import registry_from_config
from .print_builtins import apply_builtin
from .print_slash import expand_slash

if TYPE_CHECKING:
    from ..engines.agent.loop import AgentOutcome
    from .print_run import _Run


@dataclass(frozen=True, slots=True)
class TurnPrompt:
    """Hazırlanan tur: `reply` doluysa model çağrılmadan bu metinle biter."""

    task: str
    reply: str | None = None


def catalog(run: _Run) -> CapabilityRegistry:
    """Beceri/ajan kataloğu (`--bare`/`--safe-mode`'da yalnız oturumluk ajanlar)."""
    plan = run.plan
    if plan.request.bare or plan.request.safe_mode:
        from .print_runtime import bare_catalog

        extra = plan.request.add_dir if plan.request.bare else ()
        return bare_catalog(plan.config, extra, plan.session_agents)
    return registry_from_config(
        plan.config,
        Path.home(),
        run.root,
        session_agents=plan.session_agents,
        extra_roots=plan.request.add_dir,
        headless=True,
    )


def prepare_turn(run: _Run, task: str) -> TurnPrompt:
    """İstemi tura hazırla; `run.slash` bu turun genişletmesiyle değişir."""
    run.slash = None
    if run.plan.request.disable_slash:
        return TurnPrompt(task)
    reply = apply_builtin(run, task)
    if reply is not None:
        return TurnPrompt(task, reply=reply)
    if run.capabilities is None:
        run.capabilities = catalog(run)
    plan = run.plan
    run.slash = expand_slash(
        task,
        run.capabilities,
        config=plan.config,
        mode=plan.mode,
        root=run.root,
        session_id=run.session.session_id,
    )
    if run.slash.error:
        return TurnPrompt(task, reply=run.slash.error)
    return TurnPrompt(run.slash.task)


def turn_tools(run: _Run) -> tuple[set[str] | None, frozenset[str], str]:
    """Planın araç kümesi + `/beceri` daraltması: (izinli, yasak, ek sistem)."""
    selection, slash = run.plan.selection, run.slash
    allowed = set(selection.allowed) if selection.allowed is not None else None
    if slash is None:
        return allowed, selection.denied, ""
    if slash.allowed_tools is not None:
        allowed = set(slash.allowed_tools) if allowed is None else allowed & slash.allowed_tools
    return allowed, selection.denied | slash.denied_tools, slash.extra_system


def fork_runner(run: _Run) -> Callable[..., Awaitable[AgentOutcome]] | None:
    """`/<beceri>` `context: fork` ise tur fork alt ajanda koşar (REPL `/subtask` yolu, #289)."""
    slash = run.slash
    if slash is None or not slash.fork:
        return None
    from ..engines.agent.team_fork import run_forked_turn

    if run.stream is not None:
        run.stream.expect_forked_command(slash.skill_name)
    if slash.fork_agent:
        return functools.partial(run_forked_turn, persona=slash.fork_agent)
    return run_forked_turn

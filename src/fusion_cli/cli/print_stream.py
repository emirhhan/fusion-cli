"""`--input-format stream-json` koşusu: her kullanıcı satırı bir tur (#280).

stdin `ControlChannel` ile ayrı iş parçacığında okunur: tur sürerken gelen `interrupt`
turu keser (sonuç `error_during_execution`, hata `[Request interrupted by user]`),
`set_permission_mode` / `set_model` sonraki turdan geçerli olur, `--permission-prompt-tool
stdio` onayları `can_use_tool` denetim isteğiyle sorulur.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from typing import TYPE_CHECKING

from ..engines.agent.loop import AgentOutcome
from ..ui import print_messages as texts
from . import sdk_messages as sdk
from .print_builtins import apply_builtin
from .print_control import ControlChannel

if TYPE_CHECKING:
    from .print_run import _Run


def stream_turns(run: _Run) -> int:
    """Kullanıcı satırlarını sırayla tur olarak koş; son turun çıkış kodunu döndür."""
    from .print_run import _finish, _turn

    stream = run.stream
    assert stream is not None
    channel = ControlChannel(sys.stdin, stream.write).start()
    run.control = channel
    code = 0
    for task, raw in channel.users():
        _apply_controls(run, channel)
        if run.plan.request.replay_user:
            stream.write(sdk.user_message(run.session.session_id, raw))
        reply = None if run.plan.request.disable_slash else apply_builtin(run, task)
        if reply is not None:
            code = _finish(
                run, task, AgentOutcome(final_text=reply, messages=[], ok=True), None, ()
            )
            continue
        try:
            code = _finish(run, task, *_turn(run, task))
        except asyncio.CancelledError:
            if not channel.interrupted:
                raise
            code = _finish(run, task, *_interrupted())
    return code


def _interrupted() -> tuple[AgentOutcome, None, tuple[str, ...]]:
    outcome = AgentOutcome(final_text="", messages=[], ok=False)
    return outcome, None, (texts.PRINT_INTERRUPTED,)


def _apply_controls(run: _Run, channel: ControlChannel) -> None:
    """`set_permission_mode` / `set_model` isteklerini sonraki tura uygula."""
    from .print_options import apply_model, parse_permission_mode

    plan = run.plan
    if channel.mode is not None:
        plan = replace(plan, mode=parse_permission_mode(channel.mode, skip_permissions=False))
        channel.mode = None
    if channel.model is not None:
        plan = replace(plan, config=apply_model(plan.config, channel.model, None))
        channel.model = None
    run.plan = plan

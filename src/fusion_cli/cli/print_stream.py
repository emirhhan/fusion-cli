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

from ..engines.agent.approval import ApprovalMode
from ..engines.agent.loop import AgentOutcome
from ..ui import print_messages as texts
from . import print_options
from . import sdk_messages as sdk
from .print_control import ControlChannel
from .print_turn import prepare_turn

if TYPE_CHECKING:
    from .print_run import _Run


def stream_turns(run: _Run) -> int:
    """Kullanıcı satırlarını sırayla tur olarak koş; son turun çıkış kodunu döndür."""
    from .print_run import _finish, _turn, replied

    stream = run.stream
    assert stream is not None
    request = run.plan.request
    channel = ControlChannel(
        sys.stdin,
        stream.write,
        bypass_allowed=bool(
            request.skip_permissions or request.allow_skip or run.plan.mode is ApprovalMode.BYPASS
        ),
        restricted=request.restricted,
        check_model=lambda model: print_options.apply_model(run.plan.config, model, None),
    ).start()
    run.control = channel
    code = 0
    for task, raw in channel.users():
        _apply_controls(run, channel)
        if run.plan.request.replay_user:
            stream.write(sdk.user_message(run.session.session_id, raw))
        prepared = prepare_turn(run, task)
        if prepared.reply is not None:
            code = _finish(run, task, replied(prepared.reply), None, ())
            continue
        try:
            code = _finish(run, task, *_turn(run, prepared.task))
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
    from .print_options import parse_permission_mode

    plan = run.plan
    if channel.mode is not None:
        plan = replace(plan, mode=parse_permission_mode(channel.mode, skip_permissions=False))
        channel.mode = None
    if channel.model is not None:
        model, channel.model = channel.model, None
        try:
            plan = replace(plan, config=print_options.apply_model(plan.config, model, None))
        except ValueError as error:  # istekte doğrulandı; ayar arada değiştiyse tur sürer
            from .print_run import _warn

            _warn(str(error))
    run.plan = plan

"""Target identity failures remain blocked and return actionable local guidance."""

from dataclasses import replace

import pytest

from fusion_cli.core.desktop_settings import DesktopLevel
from fusion_cli.core.tools import Tool, ToolEffect, ToolResult
from fusion_cli.engines.agent import desktop_approval, loop
from fusion_cli.engines.agent.approval import ApprovalRequest, Decision
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.tools.desktop_policy import UNVERIFIED_REASON, DesktopAssessment

from .fakes import tool_call
from .test_desktop_visual_grounding import _setup


@pytest.mark.parametrize(
    "name,args",
    [
        ("desktop_key", {"key": "3"}),
        ("desktop_background_action", {"action": "press", "pid": 0}),
    ],
)
async def test_unverified_key_request_stays_blocked_and_explains_target_recovery(
    tmp_path, name, args
):
    deps, state, registry, posted = _setup(tmp_path)
    deps.tool_context.desktop.focus_required = True
    registry.register(
        Tool(
            name,
            "",
            {"type": "object"},
            lambda args, _ctx: posted.append(args) or ToolResult("posted"),
            mutating=True,
            effect=ToolEffect.REMOTE_WRITE,
        )
    )
    result, outcome = await loop._execute(
        tool_call(name, **args),
        args,
        deps,
        registry,
        execution=ExecutionPolicy(is_web=False),
        state=state,
    )
    assert not result.ok and outcome is loop.ToolOutcome.BLOCKED and not posted
    assert "desktop_window_focus" in result.output
    assert "window_id" in result.output and "pid" in result.output
    assert "desktop_screenshot" in result.output
    assert "Ayarlar" not in result.output
    assert "Bu uygulamada bu eylemi deneme" not in result.output


@pytest.mark.parametrize(
    "reason,local",
    [
        (UNVERIFIED_REASON, False),
        (UNVERIFIED_REASON + "; denied", True),
        (UNVERIFIED_REASON + " ", True),
        ("remote: " + UNVERIFIED_REASON, True),
        ("Fusion kendi penceresini yönetemez", True),
        ("Calculator reddedilen uygulamalar listesinde", True),
        ("Safari için kademe bak, bu eylem yaz ister", True),
        ("yetenek engeli", True),
    ],
)
def test_other_denials_cannot_gain_target_recovery_advice(reason, local):
    tool = Tool("desktop_key", "", {}, lambda *_: ToolResult("unused"))
    request = ApprovalRequest(tool, {}, danger=None, pre_denied=reason)
    if local:
        request = desktop_approval.apply_desktop(
            replace(request, pre_denied=None),
            DesktopAssessment(DesktopLevel.FULL, blocked=reason),
        )
    message = loop._decision_message(Decision.BLOCKED, plan_mode=False, request=request)
    assert "desktop_window_focus" not in message
    assert "desktop_screenshot" not in message


def test_prior_permission_rule_cannot_be_reclassified_as_target_recovery():
    tool = Tool("desktop_key", "", {}, lambda *_: ToolResult("unused"))
    request = desktop_approval.apply_desktop(
        ApprovalRequest(tool, {}, danger=None, pre_denied=UNVERIFIED_REASON),
        DesktopAssessment(DesktopLevel.FULL, blocked=UNVERIFIED_REASON),
    )
    assert not request.desktop_blocked
    message = loop._decision_message(Decision.BLOCKED, plan_mode=False, request=request)
    assert "desktop_window_focus" not in message
    assert "desktop_screenshot" not in message


def test_human_denial_takes_precedence_over_target_recovery():
    tool = Tool("desktop_key", "", {}, lambda *_: ToolResult("unused"))
    request = desktop_approval.apply_desktop(
        ApprovalRequest(tool, {}, danger=None),
        DesktopAssessment(DesktopLevel.FULL, blocked=UNVERIFIED_REASON),
    )
    message = loop._decision_message(Decision.DENIED, plan_mode=False, request=request)
    assert "desktop_window_focus" not in message
    assert "desktop_screenshot" not in message

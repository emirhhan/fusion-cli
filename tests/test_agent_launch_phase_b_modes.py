"""dontAsk kipinde izin verilmemiş çağrı sorulmadan engellenir."""

from __future__ import annotations

import dataclasses

import pytest

from fusion_cli.config.agent_launch_settings import AgentLaunchConfig
from fusion_cli.engines.agent import team_settings
from fusion_cli.engines.agent.approval import (
    ApprovalRequest,
    Decision,
    build_policy,
    parse_mode,
)
from fusion_cli.engines.agent.team import GENERIC_PERSONA
from tests.test_team_settings import _deps, _Tool


async def test_dontask_acik_izni_korur_soruyu_tehlikeyi_ve_sorulacak_islemi_engeller():
    class ForbiddenPrompter:
        async def confirm(self, request):
            pytest.fail("dontAsk kullanıcıya sormamalı")

    policy = build_policy(parse_mode("dontAsk"), ForbiddenPrompter())
    request = ApprovalRequest(tool=_Tool(), args={}, danger=None)
    assert await policy.decide(request) is Decision.BLOCKED
    assert await policy.decide(dataclasses.replace(request, pre_allowed=True)) is Decision.ALLOW
    assert await policy.decide(dataclasses.replace(request, read_only=True)) is Decision.ALLOW
    assert (
        await policy.decide(dataclasses.replace(request, pre_allowed=True, danger="tehlike"))
        is Decision.ALLOW  # #84: allow kuralı sezgisel tehlikeyi açar
    )
    assert (
        await policy.decide(dataclasses.replace(request, pre_allowed=True, critical="kritik"))
        is Decision.BLOCKED
    )
    assert await policy.decide(dataclasses.replace(request, danger="tehlike")) is Decision.BLOCKED
    assert (
        await policy.decide(dataclasses.replace(request, pre_allowed=True, pre_ask="kural"))
        is Decision.BLOCKED
    )


def test_dontask_ust_bypassa_yukselemez(tmp_path):
    deps, built = _deps(tmp_path, mode=parse_mode("dontAsk"))
    persona = dataclasses.replace(GENERIC_PERSONA, permission_mode="bypassPermissions")
    team_settings.child_policies(deps, persona, "çocuk")
    assert built == [parse_mode("dontAsk")]
    assert team_settings.child_approval_mode(deps, persona)() is parse_mode("dontAsk")


@pytest.mark.parametrize("parent", ("default", "dontAsk"))
def test_kapali_auto_istegi_ustun_politikasini_korur(tmp_path, parent):
    deps, built = _deps(tmp_path, mode=parse_mode(parent))
    deps.config = dataclasses.replace(
        deps.config, agent_launch=AgentLaunchConfig(disable_auto_mode=True)
    )
    persona = dataclasses.replace(GENERIC_PERSONA, permission_mode="auto")
    team_settings.child_policies(deps, persona, "çocuk")
    assert built == [parse_mode(parent)]
    assert team_settings.child_approval_mode(deps, persona)() is parse_mode(parent)

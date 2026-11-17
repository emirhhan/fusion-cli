"""Alt ajan model seçimi ve güncel izin aktarımı sözleşmesi."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from fusion_cli.core.errors import ConfigError
from fusion_cli.core.turn_deadline import TurnDeadline
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import team_settings
from fusion_cli.engines.agent.approval import (
    ApprovalAnswer,
    ApprovalMode,
    ApprovalRequest,
    Decision,
    build_policy,
)
from fusion_cli.engines.agent.attempts import InvocationBudget
from fusion_cli.engines.agent.loop import _new_budget
from fusion_cli.engines.agent.team import GENERIC_PERSONA, resolve_persona, spawn_agent_tool
from fusion_cli.tools import capabilities, plugin_capabilities
from tests.test_team_settings import _deps, _Tool


def test_farkli_aile_takma_adi_yapilandirilmis_modeli_secer():
    parent = ModelSpec("üst", "anthropic/claude-opus-custom[1m]")
    candidate = ModelSpec("sonnet", "openrouter/anthropic/claude-sonnet-custom")
    persona = dataclasses.replace(GENERIC_PERSONA, model="sonnet")

    chosen = team_settings.child_model(persona, parent, candidates=(candidate,))

    assert chosen is not None and chosen.model == candidate.model
    assert chosen.fallback == parent.models


@pytest.mark.parametrize("alias", ("sonnet", "opus", "haiku", "fable"))
def test_ayni_aile_takma_adi_ustun_tam_kimligini_korur(alias):
    parent = ModelSpec("üst", f"anthropic/claude-{alias}-custom[1m]")
    candidate = ModelSpec(alias, f"anthropic/claude-{alias}-other")
    persona = dataclasses.replace(GENERIC_PERSONA, model=alias)
    assert team_settings.child_model(persona, parent, candidates=(candidate,)) is parent


@pytest.mark.parametrize("model", ("", "inherit", "INHERIT"))
def test_miras_ustun_etkin_model_nesnesini_korur(model):
    parent = ModelSpec("üst", "sahte/etkin")
    assert (
        team_settings.child_model(dataclasses.replace(GENERIC_PERSONA, model=model), parent)
        is parent
    )


def test_egik_cizgisiz_claude_kimligi_saglayiciya_cozulur():
    parent = ModelSpec("üst", "sahte/ücretsiz")
    persona = dataclasses.replace(GENERIC_PERSONA, model="claude-sonnet-configured[1m]")
    chosen = team_settings.child_model(persona, parent)
    assert chosen is not None and chosen.model == "anthropic/claude-sonnet-configured[1m]"
    assert chosen.fallback == parent.models


def test_yapilandirilmamis_takma_adi_sessizce_miras_olmaz():
    parent = ModelSpec("üst", "sahte/ücretsiz")
    with pytest.raises(ConfigError, match="sonnet"):
        team_settings.child_model(dataclasses.replace(GENERIC_PERSONA, model="sonnet"), parent)


@pytest.mark.parametrize("model", ("sonnet", "claude-opus-custom", "openrouter/a/b"))
def test_kati_degerlendirme_ust_model_kimligini_korur(model):
    parent = ModelSpec("değerlendirme", "sahte/sabit", tags=("strict",))
    assert (
        team_settings.child_model(dataclasses.replace(GENERIC_PERSONA, model=model), parent)
        is parent
    )


@pytest.mark.parametrize("parent", tuple(ApprovalMode))
@pytest.mark.parametrize("requested", tuple(ApprovalMode))
def test_guncel_izin_matrisi_politika_ve_kip_okuyucusunda_aynidir(tmp_path, parent, requested):
    deps, built = _deps(tmp_path, mode=parent)
    expected = (
        requested
        if parent in (ApprovalMode.SECURITY, ApprovalMode.DONT_ASK)
        and requested is not ApprovalMode.BYPASS
        else parent
    )
    persona = dataclasses.replace(GENERIC_PERSONA, permission_mode=requested.value)

    _, factory = team_settings.child_policies(deps, persona, "çocuk")
    reader = team_settings.child_approval_mode(deps, persona)

    assert built == [expected]
    assert reader is not None and reader() is expected
    assert factory is not None
    factory()
    assert built == [expected, expected]


@pytest.mark.parametrize("parent", (ApprovalMode.SECURITY, ApprovalMode.PLAN))
async def test_gercek_alt_ajan_yolu_bypass_istegiyle_yetki_yukseltmez(tmp_path, parent):
    deps, _ = _deps(tmp_path, mode=parent)
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "denetci.md").write_text(
        "---\nname: denetci\ndescription: denetler\n"
        "permissionMode: bypassPermissions\n---\nİncele.",
        encoding="utf-8",
    )
    observed = []

    async def run(task, child, **kwargs):
        observed.append(child.approval_mode())
        assert child.budget is deps.budget
        assert child.invocation_budget is deps.invocation_budget
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=0)

    result = await spawn_agent_tool(deps, depth=0, run_agent=run).run(
        {"task": "incele", "uzman": "denetci"}, deps.tool_context
    )
    assert "bitti" in result.output
    assert observed == [parent]


@pytest.mark.parametrize(
    ("parent_family", "requested"),
    (("opus", "haiku"), ("haiku", "sonnet"), ("opus", "opus"), ("sonnet", "inherit")),
)
@pytest.mark.parametrize("is_strict", (False, True))
async def test_gercek_alt_ajan_yolu_etkin_ust_ve_istenen_aileyi_cozer(
    tmp_path, parent_family, requested, is_strict
):
    deps, _ = _deps(tmp_path)
    parent = ModelSpec(
        "etkin",
        f"anthropic/claude-{parent_family}-custom[1m]",
        tags=("strict",) if is_strict else (),
    )
    candidate = ModelSpec(requested, f"anthropic/claude-{requested}-configured")
    deps.active_model_override = parent
    deps.budget = _new_budget(deps.config)
    deps.budget.model_calls = 2
    deps.invocation_budget = InvocationBudget(
        limit=5, used=2, requested_spec=parent if is_strict else None
    )
    deps.deadline = TurnDeadline(deps.clock, deps.clock.monotonic() + 30)
    deps.config = dataclasses.replace(deps.config, candidates=(candidate,))
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "denetci.md").write_text(
        f"---\nname: denetci\ndescription: denetler\nmodel: {requested}\n---\nİncele.",
        encoding="utf-8",
    )
    observed = []

    async def run(task, child, **kwargs):
        observed.append(child.active_model_override)
        assert child.budget is deps.budget
        assert child.budget.model_calls == 2
        assert child.invocation_budget is deps.invocation_budget
        assert child.invocation_budget.used == 2
        assert child.invocation_budget.requested_spec is (parent if is_strict else None)
        assert child.deadline is deps.deadline
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=0)

    result = await spawn_agent_tool(deps, depth=0, run_agent=run).run(
        {"task": "incele", "uzman": "denetci"}, deps.tool_context
    )
    assert "bitti" in result.output
    expected = (
        parent.model if is_strict or requested in (parent_family, "inherit") else candidate.model
    )
    assert len(observed) == 1 and observed[0].model == expected


async def test_gercek_alt_ajan_yolu_cozulmeyen_model_icin_duzeltme_yolunu_gosterir(tmp_path):
    deps, _ = _deps(tmp_path)
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "denetci.md").write_text(
        "---\nname: denetci\ndescription: denetler\nmodel: haiku\n---\nİncele.", encoding="utf-8"
    )

    async def forbidden(task, child, **kwargs):
        pytest.fail("Çözülemeyen model sağlayıcı çağrısına ulaşmamalı")

    result = await spawn_agent_tool(deps, depth=0, run_agent=forbidden).run(
        {"task": "incele", "uzman": "denetci"}, deps.tool_context
    )
    assert "haiku" in result.output
    assert "candidates" in result.output and "sağlayıcı/model" in result.output


def _agent_from_source(tmp_path, monkeypatch, requested, is_plugin):
    agents = tmp_path / ("eklenti/agents" if is_plugin else ".claude/agents")
    agents.mkdir(parents=True)
    agent_path = agents / "denetci.md"
    agent_path.write_text(
        f"---\nname: denetci\ndescription: denetler\npermissionMode: {requested}\n---\nİncele.\n",
        encoding="utf-8",
    )
    inventory = SimpleNamespace(
        layout=SimpleNamespace(
            agents=(agent_path,),
            skills=(),
            commands=(),
            root=agent_path.parent.parent,
            manifest=SimpleNamespace(agents=("agents",)),
        ),
        record=SimpleNamespace(name="rapor"),
    )
    monkeypatch.setattr(
        plugin_capabilities, "active_plugins", lambda: (inventory,) if is_plugin else ()
    )
    monkeypatch.setattr(capabilities, "state_signature", lambda: ())
    return "rapor:denetci" if is_plugin else "denetci"


@pytest.mark.parametrize("requested", ("auto", "acceptEdits"))
@pytest.mark.parametrize("is_plugin", (True, False))
async def test_eklenti_izin_istegi_ust_politikayi_asamaz_proje_istegi_korunur(
    tmp_path, monkeypatch, requested, is_plugin
):
    name = _agent_from_source(tmp_path, monkeypatch, requested, is_plugin)
    deps, _ = _deps(tmp_path, mode=ApprovalMode.SECURITY)
    prompts = []

    class DenyPrompter:
        async def confirm(self, request):
            prompts.append(request)
            return ApprovalAnswer.DENY

    deps.policy_for_mode = lambda mode: build_policy(mode, DenyPrompter())
    deps.policy = deps.policy_for_mode(ApprovalMode.SECURITY)
    deps.policy_factory = lambda: build_policy(ApprovalMode.SECURITY, DenyPrompter())
    deps.tool_context = dataclasses.replace(
        deps.tool_context, write_scope=(tmp_path,), block_writes_outside_root=True
    )
    capability = deps.capabilities.get_agent(name)
    assert capability is not None
    assert (capability.source == plugin_capabilities.PLUGIN_SOURCE) is is_plugin
    request = ApprovalRequest(tool=_Tool(), args={"path": "x.py"}, danger=None)
    observed = []

    async def run(task, child, **kwargs):
        reader = team_settings.child_approval_mode(child, GENERIC_PERSONA)
        assert child.policy_factory is not None and reader is not None
        observed.append(
            (
                child.approval_mode(),
                await child.policy.decide(request),
                await child.policy_factory().decide(request),
                reader(),
            )
        )
        assert child.tool_context.write_scope == deps.tool_context.write_scope
        assert child.tool_context.block_writes_outside_root
        return SimpleNamespace(final_text="bitti", ok=True, tool_calls_made=0)

    result = await spawn_agent_tool(deps, depth=0, run_agent=run).run(
        {"task": "incele", "uzman": name}, deps.tool_context
    )
    assert "bitti" in result.output
    expected_mode = (
        ApprovalMode.SECURITY
        if is_plugin
        else team_settings.requested_mode(resolve_persona(deps.capabilities, name))
    )
    expected_decision = Decision.DENIED if is_plugin else Decision.ALLOW
    assert observed == [(expected_mode, expected_decision, expected_decision, expected_mode)]
    assert len(prompts) == (2 if is_plugin else 0)
    assert resolve_persona(deps.capabilities, name).permission_mode == (
        "" if is_plugin else requested
    )

"""Güvenilir ayarlar gerçek agent araç yüzeyine ulaşır."""

from __future__ import annotations

from dataclasses import replace

import pytest
import yaml

from fusion_cli.config import loader
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.tools import Tool, ToolResult
from fusion_cli.engines.agent.loop import run_agent

from .fakes import RecordingSink, ScriptedProvider, model_result
from .test_agent_loop import TAM_CEVAP, _deps, _kur


@pytest.fixture
def runtime_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(loader, "load_environment", lambda: None)

    def build(**runtime):
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump({"runtime": runtime}), encoding="utf-8")
        return loader.load_config(path)

    return build


def test_runtime_defaults_preserve_existing_selection(runtime_config):
    runtime = runtime_config().runtime
    assert runtime.external_tool_selection == "registration_order"
    assert runtime.symbol_query_enabled is False
    assert runtime.localization_cards is False
    assert runtime.lsp_server.command == ()
    assert runtime.lsp_server.timeout_s == 8.0


@pytest.mark.parametrize(
    "runtime",
    [
        {"external_tool_selection": "random"},
        {"symbol_query_enabled": "true"},
        {"localization_cards": 1},
        {"lsp_server": {"command": [""]}},
        {"lsp_server": {"command": ["x\x00y"]}},
        {"lsp_server": {"command": "shell"}},
        {"lsp_server": {"timeout_s": 0}},
        {"lsp_server": {"timeout_s": float("inf")}},
        {"lsp_server": {"timeout_s": float("nan")}},
        {"lsp_server": {"unknown": True}},
    ],
)
def test_runtime_rejects_invalid_tool_settings(runtime_config, runtime):
    with pytest.raises(ConfigError):
        runtime_config(**runtime)


@pytest.mark.parametrize("order", range(20))
async def test_real_agent_applies_relevance_and_denied_tools(
    tmp_path, monkeypatch, runtime_config, order
):
    provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))
    deps = _deps(tmp_path, RecordingSink())
    config = runtime_config(external_tool_selection="relevance", compact_external_tools=1)
    deps.config = replace(
        deps.config,
        agent=replace(deps.config.agent, tags=("compact", "strict")),
        runtime=replace(config.runtime, project_instructions=False),
    )
    numbers = list(range(40))
    numbers = numbers[order:] + numbers[:order]
    if order % 2:
        numbers.reverse()
    for number in numbers:
        name = f"remote__ordinary_{number:02d}"
        deps.base_registry.register_or_replace(
            Tool(name, "Genel yardımcı", {}, lambda a, c: ToolResult("ok"))
        )
    deps.base_registry.register_or_replace(
        Tool("remote__needle", "Needle teslimat araması", {}, lambda a, c: ToolResult("ok"))
    )
    deps.base_registry.register_or_replace(
        Tool("remote__forbidden", "Needle teslimat araması", {}, lambda a, c: ToolResult("ok"))
    )
    deps.denied_tools = frozenset({"remote__forbidden"})
    await run_agent("Needle teslimat bilgisi", deps, self_review=False, verify=False)
    names = {schema["function"]["name"] for schema in provider.seen_requests[0]}
    assert "remote__needle" in names
    assert "remote__forbidden" not in names
    assert not any(name.startswith("remote__ordinary") for name in names)


def test_remote_origin_survives_disabled_tool_filter():
    from fusion_cli.engines.agent.engine_tools import _without
    from fusion_cli.tools import ToolRegistry

    registry = ToolRegistry()
    registry.register(Tool("disabled", "Kapalı", {}, lambda a, c: ToolResult("ok")))
    registry.register_or_replace(Tool("remote__kept", "Uzak", {}, lambda a, c: ToolResult("ok")))
    kept = _without(registry, frozenset({"disabled"}))
    assert kept.is_remote("remote__kept")
    assert kept.get("disabled") is None


def test_lsp_command_is_removed_from_untrusted_project_config(tmp_path, monkeypatch):
    from fusion_cli.config import trust

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(loader, "load_environment", lambda: None)
    monkeypatch.setattr(
        trust, "resolve_project_trust", lambda root: trust.TrustState(False, "güvenilmedi")
    )
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "runtime": {
                    "symbol_query_enabled": True,
                    "lsp_server": {"command": ["forbidden-server"]},
                }
            }
        )
    )
    config = loader.load_config()
    assert config.runtime.symbol_query_enabled is False
    assert config.runtime.lsp_server.command == ()


def test_explicit_lsp_config_is_trusted_and_other_tuple_fields_keep_scalar(runtime_config):
    config = runtime_config(
        symbol_query_enabled=True,
        lsp_server={"command": ["local-server", "--stdio"]},
        verification_commands="pytest",
    )
    assert config.runtime.lsp_server.command == ("local-server", "--stdio")
    assert config.runtime.verification_commands == ("pytest",)


@pytest.mark.parametrize(
    "selection,expected", [(None, "remote__first"), ("relevance", "remote__needle")]
)
async def test_actual_default_and_explicit_tool_gates(
    tmp_path, monkeypatch, runtime_config, selection, expected
):
    provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))
    old = _deps(tmp_path, RecordingSink())
    config = runtime_config(
        compact_external_tools=1, **({"external_tool_selection": selection} if selection else {})
    )
    old.config = replace(
        old.config,
        agent=replace(old.config.agent, tags=("compact", "strict")),
        runtime=replace(config.runtime, project_instructions=False),
    )
    for name, description in [
        ("remote__first", "Genel"),
        ("remote__needle", "needle araması"),
        ("remote__explicit", "İstenen"),
        ("remote__denied", "needle araması"),
    ]:
        old.base_registry.register_or_replace(
            Tool(name, description, {}, lambda a, c: ToolResult("ok"))
        )
    old.denied_tools = frozenset({"remote__denied"})
    await run_agent("needle bilgisi", old, self_review=False, verify=False)
    names = {schema["function"]["name"] for schema in provider.seen_requests[0]}
    assert names.intersection(
        {"remote__first", "remote__needle", "remote__explicit", "remote__denied"}
    ) == {expected}
    provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))
    await run_agent(
        "needle bilgisi",
        old,
        allowed_tools={"remote__explicit", "remote__denied"},
        self_review=False,
        verify=False,
    )
    names = {schema["function"]["name"] for schema in provider.seen_requests[0]}
    assert "remote__explicit" in names and "remote__denied" not in names


@pytest.mark.parametrize(
    "command,timeout",
    [("shell", 1), (("",), 1), (("server",), 0), (("server",), "slow"), (("server",), True)],
)
def test_direct_lsp_constructor_rejects_invalid_command_and_timeout(command, timeout):
    from fusion_cli.config.models import LspServerConfig

    with pytest.raises(ConfigError):
        LspServerConfig(command=command, timeout_s=timeout)


async def test_disabled_cards_remove_previous_runtime_carrier_from_provider_history(
    tmp_path, monkeypatch
):
    from .fakes import tool_call

    (tmp_path / "target.py").write_text("def target():\n    return 1\n")
    deps = _deps(tmp_path, RecordingSink())
    deps = replace(
        deps,
        config=replace(
            deps.config,
            runtime=replace(
                deps.config.runtime,
                localization_cards=True,
                project_instructions=False,
                repo_map_chars=0,
            ),
        ),
    )
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("search_code", pattern="target", path="target.py")]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    previous = await run_agent("target.py konumunu incele", deps, self_review=False, verify=False)
    disabled = replace(
        deps,
        config=replace(deps.config, runtime=replace(deps.config.runtime, localization_cards=False)),
    )
    provider = _kur(monkeypatch, ScriptedProvider([model_result("İstenen bilgi hazır.")]))
    await run_agent(
        "Yeni bilgiyi özetle", disabled, history=previous.messages, self_review=False, verify=False
    )
    assert not any(
        message.content.startswith("KANITLI YER BELİRLEME KARTI")
        for message in provider.seen_messages[0]
    )

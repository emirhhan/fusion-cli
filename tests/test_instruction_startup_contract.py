"""Startup diagnostics count loaded rules and honor explicit instruction policy."""

import asyncio
from types import SimpleNamespace

import pytest

from fusion_cli.appserver import instructions, voice
from fusion_cli.engines.agent.instruction_audit import audit_instructions
from fusion_cli.engines.agent.instruction_rules import discover_rules
from fusion_cli.engines.agent.project_instructions import load_all_instructions


@pytest.fixture
def source_tree(tmp_path):
    root, home = tmp_path / "project", tmp_path / "home"
    for base in (root, home):
        (base / ".claude/rules").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("pytest", encoding="utf-8")
    (home / ".claude/rules/global.md").write_text("Always speak clearly", encoding="utf-8")
    (root / ".claude/rules/global.md").write_text("Check results", encoding="utf-8")
    (root / ".claude/rules/scoped.md").write_text(
        "---\npaths: [src/**]\n---\nDeferred guidance", encoding="utf-8"
    )
    return root, home


def managed_only(home):
    (home / ".claude/settings.json").write_text(
        '{"pluginConfigs":{"cc-plugin-agents-md@builtin":'
        '{"options":{"instructionFiles":"managed-only"}}}}',
        encoding="utf-8",
    )


def test_startup_files_and_audit_count_only_loaded_rules(source_tree):
    root, home = source_tree
    loaded = load_all_instructions(root, home, include_external_memory=False)
    assert "Always speak clearly" in loaded.text
    assert "Check results" in loaded.text
    assert "Deferred guidance" not in loaded.text
    assert {item.label for item in loaded.files} == {
        "CLAUDE.md",
        "~/.claude/rules/global.md",
        ".claude/rules/global.md",
    }
    assert sum(item.chars for item in loaded.files) == 39
    audit = audit_instructions(root, home)
    assert audit.total_chars == 39
    assert audit.rules == 3


def test_settings_total_counts_startup_rules_without_deferred_rules(source_tree, monkeypatch):
    root, home = source_tree
    monkeypatch.setattr(voice, "_data_home", lambda: home / "data")
    result = instructions.get_instructions(root, home)
    assert result["toplam_karakter"] == 39
    assert len(result["katmanlar"]) == 4
    scoped = next(row for row in result["katmanlar"] if row["kaynak"].endswith("scoped.md"))
    assert scoped["kapsam"] == ["src/**"]


def test_managed_only_suppresses_ordinary_rules_and_diagnostics(source_tree, monkeypatch):
    root, home = source_tree
    managed_only(home)
    monkeypatch.setattr(voice, "_data_home", lambda: home / "data")
    assert discover_rules(root, home) == ()
    loaded = load_all_instructions(root, home, include_external_memory=False)
    assert "Always speak clearly" not in loaded.text
    assert "Check results" not in loaded.text
    assert audit_instructions(root, home).rules == 0
    assert instructions.get_instructions(root, home)["toplam_karakter"] == 0


@pytest.mark.parametrize("additional", [False, True])
def test_managed_only_suppresses_deferred_nested_and_extra_rules(
    source_tree, monkeypatch, additional
):
    from fusion_cli.engines.agent.loop import _inject_nested_instructions

    root, home = source_tree
    managed_only(home)
    extra = root.parent / "extra"
    extra.mkdir()
    monkeypatch.setenv("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", "1")
    (extra / ".claude/rules").mkdir(parents=True)
    (extra / ".claude/rules/match.md").write_text(
        "---\npaths: [src/**]\n---\nAdditional guidance", encoding="utf-8"
    )
    child = (extra if additional else root) / "src"
    child.mkdir()
    (child / "CLAUDE.md").write_text("Nested guidance", encoding="utf-8")
    target = child / "code.py"
    target.touch()
    from fusion_cli.core.tools import ToolContext

    state = SimpleNamespace(nested_candidates=[str(target)], nested_loaded=set())
    deps = SimpleNamespace(
        tool_context=ToolContext(root=root, extra_roots=(extra,)),
        home=home,
        capabilities=None,
        publisher=SimpleNamespace(publish=lambda event: None),
        config=SimpleNamespace(runtime=SimpleNamespace(nested_instructions=True)),
    )
    messages = []
    _inject_nested_instructions(messages, deps, state)
    assert messages == []
    assert state.nested_candidates == []


async def test_startup_rule_events_preserve_user_type_without_duplicate_events(source_tree):
    from fusion_cli.engines.agent.instructions_hook import (
        notify,
        rule_startup_events,
        startup_events,
    )

    root, home = source_tree
    loaded = load_all_instructions(root, home, include_external_memory=False)
    events = startup_events(loaded.files)
    rule_events = [event for event in events if "/rules/" in event["file_path"]]
    assert len(rule_events) == 2
    assert {event["memory_type"] for event in rule_events} == {"User", "Project"}

    emitted = []

    async def emit(event, *, subjects, fields):
        emitted.append(fields)

    hooks = SimpleNamespace(emit=emit, instructions_seen=set())
    combined = [*events, *rule_startup_events(discover_rules(root, home))]
    notify(hooks, combined)
    notify(hooks, combined)
    await asyncio.sleep(0)
    assert len(emitted) == 3
    rule_emitted = [event for event in emitted if "/rules/" in event["file_path"]]
    assert len(rule_emitted) == 2
    assert {event["memory_type"] for event in rule_emitted} == {"User", "Project"}

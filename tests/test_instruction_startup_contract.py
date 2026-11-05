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


def test_rule_budget_reports_exact_omitted_content_and_skipped_sources(tmp_path):
    from fusion_cli.engines.agent.instruction_rules import RuleFile, load_unscoped_rules

    rules = []
    for name, content in (("a", "abcdefgh"), ("b", "ıö😀abcdefg  "), ("c", "not loaded")):
        path = tmp_path / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        rules.append(RuleFile(path.name, path, (), False))
    loaded = load_unscoped_rules(tuple(rules), budget=10)
    assert [item.chars for item in loaded.files] == [8, 2]
    assert [item.trimmed for item in loaded.files] == [0, 8]
    assert loaded.trimmed_chars == 8
    assert "kırpıldı" in loaded.text
    assert "okunmayan kurallar: c.md" in loaded.text


async def test_agent_reports_loaded_sources_without_claiming_budget_skipped_rules(
    source_tree, monkeypatch
):
    from fusion_cli.engines.agent import loop, project_instructions
    from fusion_cli.engines.agent.instruction_rules import load_unscoped_rules

    from .fakes import RecordingSink, ScriptedProvider, model_result
    from .test_agent_loop import _deps, _kur

    root, home = source_tree
    # Exercise the real startup path with the existing budget set small enough to skip rules.
    monkeypatch.setattr(
        project_instructions,
        "load_unscoped_rules",
        lambda rules: load_unscoped_rules(rules, budget=5),
    )
    _kur(
        monkeypatch, ScriptedProvider([model_result("Completed and verified the requested task.")])
    )
    deps = _deps(root, RecordingSink(), home=home)
    emitted = []

    from fusion_cli.core.hooks.events import HookSet
    from fusion_cli.engines.hooks.session import HookSession

    original_emit = HookSession.emit

    async def emit(self, event, *, subjects=(), fields=None, **kwargs):
        if event.value == "InstructionsLoaded":
            emitted.append(fields)
        return await original_emit(self, event, subjects=subjects, fields=fields, **kwargs)

    monkeypatch.setattr(HookSession, "emit", emit)
    deps.hooks = HookSession(root, loader=HookSet)
    await loop.run_agent("Explain the project", deps)
    await asyncio.sleep(0)
    paths = [event["file_path"] for event in emitted]
    assert str(home / ".claude/rules/global.md") in paths
    assert str(root / ".claude/rules/global.md") not in paths


def test_rule_omitted_count_excludes_frontmatter_and_survives_stream_boundaries(tmp_path):
    from fusion_cli.engines.agent.instruction_rules import RuleFile, load_unscoped_rules

    path = tmp_path / "rule.md"
    path.write_text("---\nnote: example\n---\n" + "ö" * 70_000 + "  ", encoding="utf-8")
    loaded = load_unscoped_rules((RuleFile("rule.md", path, (), False),), budget=100)
    assert loaded.files[0].chars == 79
    assert loaded.files[0].trimmed == 69_921


def test_settings_reports_loaded_rule_trim_metadata(source_tree, monkeypatch):
    from fusion_cli.engines.agent import project_instructions
    from fusion_cli.engines.agent.instruction_rules import load_unscoped_rules

    root, home = source_tree
    monkeypatch.setattr(voice, "_data_home", lambda: home / "data")
    monkeypatch.setattr(
        project_instructions,
        "load_unscoped_rules",
        lambda rules: load_unscoped_rules(rules, budget=5),
    )
    result = instructions.get_instructions(root, home)
    user_rule = next(row for row in result["katmanlar"] if row["kaynak"].startswith("~/"))
    assert user_rule["karakter"] == 5
    assert user_rule["kirpilan"] == 15
    assert result["toplam_karakter"] == 11


def test_rule_trim_metadata_counts_body_hidden_by_partial_frontmatter(tmp_path):
    from fusion_cli.engines.agent.instruction_rules import RuleFile, load_unscoped_rules

    path = tmp_path / "rule.md"
    path.write_text("---\nnote: example\n---\n0123456789", encoding="utf-8")
    loaded = load_unscoped_rules((RuleFile("rule.md", path, (), False),), budget=2)
    # Preserve legacy rendering of a prefix that stops inside the frontmatter.
    assert loaded.files[0].chars == 2
    assert loaded.files[0].trimmed == 10


def test_rule_diagnostic_scan_stops_on_a_growing_source(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import instruction_rules as rules

    class GrowingSource:
        consumed = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size=-1):
            assert size >= 0, "diagnostics must never read to EOF"
            self.consumed += size
            assert self.consumed <= rules.MAX_RULE_FILE_CHARS + 1
            return "x" * size

    source = GrowingSource()
    path = tmp_path / "growing.md"
    monkeypatch.setattr(type(path), "open", lambda *args, **kwargs: source)
    loaded = rules.load_unscoped_rules((rules.RuleFile("growing.md", path, (), False),), budget=2)
    assert loaded.files[0].chars == 2
    assert loaded.files[0].trimmed_exact is False
    assert loaded.files[0].trimmed >= 1
    assert any("kesin" in note for note in loaded.notes)


def test_oversized_rule_rpc_and_audit_expose_uncertainty(source_tree, monkeypatch):
    from fusion_cli.engines.agent import instruction_rules as rules
    from fusion_cli.engines.agent.instruction_audit import render_audit

    root, home = source_tree
    monkeypatch.setattr(voice, "_data_home", lambda: home / "data")
    # A small cap makes the same production boundary cheap to exercise.
    monkeypatch.setattr(rules, "MAX_RULE_FILE_CHARS", 8)
    result = instructions.get_instructions(root, home)
    row = next(item for item in result["katmanlar"] if item["kaynak"].startswith("~/"))
    assert row["karakter"] == 8
    assert row["kirpilan"] is None
    assert row["kirpilan_kesin"] is False
    assert row["kirpilan_alt_sinir"] == 1
    assert any("kesin" in note for note in result["notlar"])
    audit = audit_instructions(root, home)
    assert audit.trimmed_chars_exact is False
    assert "en az" in render_audit(audit)


def test_within_cap_rule_trim_count_remains_exact(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import instruction_rules as rules

    monkeypatch.setattr(rules, "MAX_RULE_FILE_CHARS", 16)
    path = tmp_path / "normal.md"
    path.write_text("ıö😀abcdefg", encoding="utf-8")
    loaded = rules.load_unscoped_rules((rules.RuleFile("normal.md", path, (), False),), budget=2)
    assert loaded.files[0].trimmed == 8
    assert loaded.files[0].trimmed_exact is True


def test_rule_diagnostic_deadline_stops_before_more_reads(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import instruction_rules as rules

    class SlowGrowingSource:
        reads = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, size):
            self.reads += 1
            return "x" * size

    source = SlowGrowingSource()
    path = tmp_path / "slow.md"
    ticks = iter((0.0, 0.0))
    monkeypatch.setattr(rules.time, "monotonic", lambda: next(ticks, 1.0))
    monkeypatch.setattr(type(path), "open", lambda *args, **kwargs: source)
    loaded = rules.load_unscoped_rules((rules.RuleFile("slow.md", path, (), False),), budget=2)
    assert source.reads == 2  # Rendered prefix and one diagnostic chunk, then deadline.
    assert loaded.files[0].trimmed_exact is False


def test_unfinished_oversized_frontmatter_does_not_invent_omitted_body_count(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import instruction_rules as rules

    monkeypatch.setattr(rules, "MAX_RULE_FILE_CHARS", 16)
    path = tmp_path / "header.md"
    path.write_text("---\nnote: " + "x" * 100 + "\n---\nbody", encoding="utf-8")
    loaded = rules.load_unscoped_rules((rules.RuleFile("header.md", path, (), False),), budget=2)
    assert loaded.files[0].trimmed_exact is False
    assert loaded.files[0].trimmed == 0
    assert any("bilinmiyor" in note for note in loaded.notes)

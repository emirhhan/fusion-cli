"""Ara ilişkili test seçimi finalin tam kapısını daraltamaz."""

from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fusion_cli.core.execution_plan import ExecutionPlan, StepStatus
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.step_verification import _gate_result, verify_plan_acceptance
from fusion_cli.engines.agent.verification import CommandVerifier
from tests.test_reproduction_wiring import _step


def _project(root):
    (root / "logic.py").write_text("def value(): return 1\n")
    (root / "test_related.py").write_text(
        "from logic import value\ndef test_related(): assert value() == 1\n"
    )
    (root / "test_unrelated.py").write_text("def test_unrelated(): assert False\n")


async def test_intermediate_selection_skips_unrelated_but_final_runs_it(tmp_path):
    _project(tmp_path)
    verifier = CommandVerifier((f"{sys.executable} -m pytest -q",), cwd=str(tmp_path), timeout_s=10)
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "logic.py")
    deps = SimpleNamespace(
        tool_context=context,
        verifier=verifier,
        config=SimpleNamespace(runtime=SimpleNamespace(related_test_selection=True)),
    )
    step = replace(
        _step(), status=StepStatus.COMPLETED, success_criteria=(), verification_checks=()
    )
    intermediate = await _gate_result(step, AgentOutcome("", [], 0), deps, None)
    assert intermediate.ok
    assert "test_related.py" in intermediate.evidence[0].command
    assert "test_unrelated.py" not in intermediate.evidence[0].command
    final = await verify_plan_acceptance(ExecutionPlan("p", "feature", (step,)), deps)
    assert not final.ok
    assert "test_unrelated" in final.evidence[0].output
    assert "test_related.py" not in final.evidence[0].command


async def test_selection_defaults_to_full_and_dynamic_import_falls_back(tmp_path):
    _project(tmp_path)
    (tmp_path / "logic.py").write_text(
        "import importlib\nvalue = lambda: importlib.import_module('os')\n"
    )
    verifier = CommandVerifier((f"{sys.executable} -m pytest -q",), cwd=str(tmp_path), timeout_s=10)
    assert not (await verifier.verify_intermediate(("logic.py",))).ok
    assert not (await verifier.verify()).ok


async def test_disabled_selection_runs_full_intermediate_gate(tmp_path):
    _project(tmp_path)
    verifier = CommandVerifier((f"{sys.executable} -m pytest -q",), cwd=str(tmp_path), timeout_s=10)
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "logic.py")
    deps = SimpleNamespace(
        tool_context=context,
        verifier=verifier,
        config=SimpleNamespace(runtime=SimpleNamespace(related_test_selection=False)),
    )
    result = await _gate_result(_step(), AgentOutcome("", [], 0), deps, None)
    assert not result.ok
    assert "test_unrelated" in result.evidence[0].output


def test_unknown_relation_falls_back_and_transitive_relation_is_selected(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import related_test_command

    _project(tmp_path)
    command = f"{sys.executable} -m pytest -q"
    assert related_test_command(tmp_path, command, ("unknown.py",)) == command
    (tmp_path / "middle.py").write_text("from logic import value\n")
    (tmp_path / "test_related.py").write_text(
        "from middle import value\ndef test_value(): assert value()\n"
    )
    selected = related_test_command(tmp_path, command, ("logic.py",))
    assert "test_related.py" in selected
    assert "test_unrelated.py" not in selected


async def test_verifier_invalidates_environment_changed_by_command(tmp_path):
    program = "from pathlib import Path; Path('pytest.ini').write_text('[pytest]\\n')"
    command = f'{sys.executable} -c "{program}"'
    verifier = CommandVerifier((command,), cwd=str(tmp_path), timeout_s=10)
    result = await verifier.verify()
    assert result.ok
    assert result.evidence[0].environment is None


async def test_selected_commands_and_scope_are_kept_in_checkpoint_manifest(tmp_path):
    from fusion_cli.core.checkpoint import StepCheckpointEvidence
    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.memory.checkpoint_evidence import evidence_payload

    _project(tmp_path)
    verifier = CommandVerifier((f"{sys.executable} -m pytest -q",), cwd=str(tmp_path), timeout_s=10)
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "logic.py")
    deps = SimpleNamespace(
        tool_context=context,
        verifier=verifier,
        config=SimpleNamespace(runtime=SimpleNamespace(related_test_selection=True)),
        execution=None,
        budget=None,
    )
    step = replace(_step(), success_criteria=(), verification_checks=())
    checked = await verify_step(step, AgentOutcome("", [], 0), deps)
    payload = evidence_payload((StepCheckpointEvidence("step", criteria=checked.criteria),))
    commands = [item["command"] for item in payload[0]["criteria"]]
    assert len(commands) == 1
    assert "test_related.py" in commands[0]
    assert "test_unrelated.py" not in commands[0]


async def test_disabling_selection_cannot_reuse_narrowed_cache(tmp_path):
    from fusion_cli.engines.agent.gate_cache import GateCache, GateScope

    _project(tmp_path)
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "logic.py")
    runtime = SimpleNamespace(related_test_selection=True)
    deps = SimpleNamespace(
        tool_context=context,
        verifier=CommandVerifier(
            (f"{sys.executable} -m pytest -q",), cwd=str(tmp_path), timeout_s=10
        ),
        config=SimpleNamespace(runtime=runtime),
    )
    gate = GateScope(GateCache())
    outcome = AgentOutcome("", [], 0)
    assert (await _gate_result(_step(), outcome, deps, gate)).ok
    runtime.related_test_selection = False
    assert not (await _gate_result(_step(), outcome, deps, gate)).ok


def test_conftest_makes_fixture_relationship_unknown_and_forces_full(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import related_test_command

    _project(tmp_path)
    (tmp_path / "conftest.py").write_text("from logic import value\n")
    command = f"{sys.executable} -m pytest -q"
    assert related_test_command(tmp_path, command, ("logic.py",)) == command


def test_package_initializer_dependencies_cover_indirect_importers(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import related_test_command

    package = tmp_path / "pkg"
    package.mkdir()
    (tmp_path / "base.py").write_text("value = 1\n")
    (package / "__init__.py").write_text("from base import value\n")
    (package / "logic.py").write_text("def answer(): return 42\n")
    (tmp_path / "test_direct.py").write_text("import pkg\n")
    (tmp_path / "test_indirect.py").write_text("from pkg.logic import answer\n")
    command = f"{sys.executable} -m pytest -q"
    selected = related_test_command(tmp_path, command, ("base.py",))
    assert selected == command or "test_indirect.py" in selected


def test_non_python_runner_is_never_rewritten(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import related_test_command

    _project(tmp_path)
    command = "echo -m pytest -q"
    assert related_test_command(tmp_path, command, ("logic.py",)) == command


def test_custom_pytest_discovery_is_unknown_and_falls_back(tmp_path):
    from fusion_cli.engines.agent.verify_discovery import related_test_command

    _project(tmp_path)
    (tmp_path / "custom_check.py").write_text("from logic import value\n")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npython_files = ["custom_*.py", "test_*.py"]\n'
    )
    command = f"{sys.executable} -m pytest -q"
    assert related_test_command(tmp_path, command, ("logic.py",)) == command


@pytest.mark.parametrize(
    "inline",
    [
        "from logic import value; assert value == 2",
        "import logic as module; assert module.value == 2",
    ],
)
async def test_inline_import_dependency_cannot_be_omitted_from_intermediate(tmp_path, inline):
    (tmp_path / "logic.py").write_text("value = 1\n")
    (tmp_path / "test_direct.py").write_text(
        "from logic import value\ndef test_direct(): assert value == 1\n"
    )
    (tmp_path / "test_inline.py").write_text(f"def test_inline(): {inline}\n")
    verifier = CommandVerifier((f"{sys.executable} -m pytest -q",), cwd=str(tmp_path), timeout_s=10)
    result = await verifier.verify_intermediate(("logic.py",))
    assert not result.ok
    assert "test_direct.py" in result.evidence[0].command
    assert "test_inline.py" in result.evidence[0].command
    assert "test_inline" in result.evidence[0].output
    assert not (await verifier.verify()).ok

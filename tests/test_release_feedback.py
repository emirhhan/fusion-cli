"""Fixed trusted verification uses ordinary CommandVerifier findings; never actor PASS."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from evals.frozen_engine import require_protected_profile
from evals.loader import load_tasks
from scripts.release_manifest import ROOT

from .test_frozen_release_profile import _profile


@pytest.fixture
def protected_host():
    with tempfile.TemporaryDirectory(prefix=".feedback-test-", dir=ROOT) as directory:
        yield Path(directory)


def test_profile_allows_only_the_fixed_inspector_command():
    from dataclasses import replace

    config = _profile()
    fixed = replace(
        config,
        runtime=replace(config.runtime, verification_commands=("fusion-inspect-production",)),
    )
    require_protected_profile(fixed, platform="darwin")
    for commands in ((), ("true",), ("fusion-inspect-production --other-root .",)):
        wrong = replace(config, runtime=replace(config.runtime, verification_commands=commands))
        with pytest.raises(ValueError):
            require_protected_profile(wrong, platform="darwin")


def _control(host, *, task_id="mcp-stdio-listele-cagir"):
    from scripts.release_feedback import prepare_feedback

    root = host / "candidate"
    root.mkdir()
    task = next(
        task for task in load_tasks(ROOT / "evals/suite/production.yaml") if task.id == task_id
    )
    profile = host / "profile.yaml"
    profile.write_bytes((ROOT / "release/acceptance-profile.yaml").read_bytes())
    control = prepare_feedback(host / "control", root, task.id, profile)
    return root, control


@pytest.mark.skipif(os.sys.platform != "darwin", reason="mandatory macOS acceptance sandbox")
async def test_normal_command_verifier_reports_actual_mcp_failure_then_passes_repair(
    protected_host, monkeypatch
):
    from fusion_cli.engines.agent.verification import CommandVerifier, build_verifier

    root, control = _control(protected_host)
    # CWD/PYTHONPATH fakes cannot override trusted wrapper or SDK imports.
    (root / "fusion-inspect-production").write_text("#!/bin/sh\nexit 0\n")
    (root / "fusion-inspect-production").chmod(0o755)
    (root / "json.py").write_text("raise SystemExit(0)\n")
    (root / "mcp_candidate.py").write_text(
        "import os\nassert 'NVIDIA_NIM_API_KEY' not in os.environ\n"
        "async def smoke(client):\n"
        "    tools = await client.list_tools()\n"
        "    next(t for t in tools if t.name == 'ping')\n"
        "    await client.call_tool('ping', {})\n"
    )
    for name, value in control.environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "SYNTHETIC_DO_NOT_FORWARD")
    verifier = build_verifier(_profile(), root=root, tool_context=None)
    assert isinstance(verifier, CommandVerifier)
    failed = await verifier.verify()
    assert not failed.ok
    assert any("AttributeError" in finding and "tuple" in finding for finding in failed.findings)
    assert "SYNTHETIC_DO_NOT_FORWARD" not in str(failed)
    (root / "mcp_candidate.py").write_text(
        "async def smoke(client):\n"
        "    tools = await client.list_tools()\n"
        "    next(t for t in tools.tools if t.name == 'ping')\n"
        "    await client.call_tool('ping', {})\n"
    )
    assert (await verifier.verify()).ok
    control.assert_unchanged()


@pytest.mark.skipif(os.sys.platform != "darwin", reason="mandatory macOS acceptance sandbox")
def test_bound_wrapper_rejects_extra_args_and_wrong_cwd(protected_host):
    root, control = _control(protected_host)
    command = str(control.wrapper)
    extra = subprocess.run(
        [command, "--task", "other"],
        cwd=root,
        env=control.environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    wrong = subprocess.run(
        [command],
        cwd=protected_host,
        env=control.environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert extra.returncode != 0 and wrong.returncode != 0


def test_host_guard_detects_wrapper_or_binding_tamper(protected_host):
    _root, control = _control(protected_host)
    control.wrapper.chmod(0o755)
    control.wrapper.write_text("#!/bin/sh\nexit 0\n")
    with pytest.raises(ValueError):
        control.assert_unchanged()


@pytest.mark.parametrize("mutation", [None, "relative_path", "wrong_binding", "cwd_wrapper"])
def test_frozen_route_rejects_path_and_environment_redirection(
    protected_host, monkeypatch, mutation
):
    import json

    from evals.feedback_binding import runtime_route

    root, control = _control(protected_host)
    raw = json.loads(control.binding.read_text())
    for name, value in control.environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("FUSION_CONFIG", raw["profile"])
    if mutation == "relative_path":
        monkeypatch.setenv("PATH", ".:" + control.environment["PATH"])
    if mutation == "wrong_binding":
        monkeypatch.setenv("FUSION_RELEASE_INSPECTOR_BINDING_SHA256", "0" * 64)
    if mutation == "cwd_wrapper":
        fake = root / "fusion-inspect-production"
        fake.write_text("#!/bin/sh\nexit 0\n")
        fake.chmod(0o555)
        monkeypatch.setenv("FUSION_RELEASE_INSPECTOR", str(fake))
    if mutation is None:
        runtime_route(root, raw["source_digest"])
    else:
        with pytest.raises(ValueError):
            runtime_route(root, raw["source_digest"])


@pytest.mark.skipif(os.sys.platform != "darwin", reason="mandatory macOS acceptance sandbox")
async def test_failed_candidate_stderr_is_bounded_and_redacted(protected_host, monkeypatch):
    from fusion_cli.engines.agent.verification import build_verifier

    root, control = _control(protected_host)
    (root / "mcp_candidate.py").write_text(
        "async def smoke(client):\n"
        "    raise RuntimeError('NVIDIA_NIM_API_KEY=synthetic-never-a-real-key')\n"
    )
    for name, value in control.environment.items():
        monkeypatch.setenv(name, value)
    result = await build_verifier(_profile(), root=root, tool_context=None).verify()
    assert not result.ok
    text = str(result.findings)
    assert "RuntimeError" in text
    assert "synthetic-never-a-real-key" not in text
    assert len(text) < 20000


@pytest.mark.skipif(os.sys.platform != "darwin", reason="mandatory macOS acceptance sandbox")
async def test_existing_agent_repair_loop_receives_real_inspector_finding(
    protected_host, monkeypatch
):
    from fusion_cli.core.events import VerificationFailed
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.verification import build_verifier

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import _deps, _kur

    root, control = _control(protected_host)
    bad = (
        "async def smoke(client):\n    tools = await client.list_tools()\n"
        "    next(t for t in tools if t.name == 'ping')\n"
        "    await client.call_tool('ping', {})\n"
    )
    good = bad.replace("for t in tools if", "for t in tools.tools if")
    scripted = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("write_file", path="mcp_candidate.py", content=bad)]
                ),
                model_result("Implemented the requested MCP callback."),
                model_result(
                    tool_calls=[tool_call("write_file", path="mcp_candidate.py", content=good)]
                ),
                model_result("Repaired the callback and verified it."),
            ]
        ),
    )
    for name, value in control.environment.items():
        monkeypatch.setenv(name, value)
    sink = RecordingSink()
    deps = _deps(root, sink)
    deps.config = _profile()
    deps.verifier = build_verifier(deps.config, root=root, tool_context=deps.tool_context)
    result = await loop.run_agent(
        "Implement the MCP callback.", deps, self_review=False, verify=True
    )
    failures = [event for event in sink.events if isinstance(event, VerificationFailed)]
    assert failures and any("AttributeError" in str(event.findings) for event in failures)
    assert result.verification_repaired is True
    assert (await deps.verifier.verify()).ok
    assert any("AttributeError" in str(messages) for messages in scripted.seen_messages)


def test_trusted_checkout_and_profile_cannot_live_in_writable_temp(protected_host, tmp_path):
    from evals.feedback_binding import assert_source_locations

    profile = protected_host / "profile.yaml"
    profile.write_text("profile")
    root = protected_host / "candidate"
    root.mkdir()
    with pytest.raises(ValueError):
        assert_source_locations(tmp_path, profile, root)
    with pytest.raises(ValueError):
        assert_source_locations(ROOT, tmp_path / "profile.yaml", root)
    with pytest.raises(ValueError):
        assert_source_locations(ROOT, profile, ROOT / "src/fusion_cli/planted-module")

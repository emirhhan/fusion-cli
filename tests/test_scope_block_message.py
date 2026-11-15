"""Kapsam dışı araç çağrısı modele neyin serbest olduğunu söylemeli."""

from __future__ import annotations

from fusion_cli.core.events import ToolOutcome
from fusion_cli.core.trace import _SCOPE_MARK
from fusion_cli.core.types import ToolCall
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
from fusion_cli.engines.agent.loop import _execute
from fusion_cli.tools import build_registry
from tests.agent_harness import web_deps
from tests.fakes import RecordingSink


async def test_kapsam_disi_arac_reddi_izin_verilen_araclari_listeler(tmp_path):
    """Gözlem turunda model reddi anlamayıp aynı yazma aracını deniyordu."""
    policy = ExecutionPolicy(is_web=True, allowed_tool_names=frozenset({"read_file", "list_dir"}))
    call = ToolCall(id="1", name="write_file", arguments="{}")

    deps = web_deps(tmp_path, RecordingSink())
    result, outcome = await _execute(call, {}, deps, build_registry(), execution=policy)

    assert outcome is ToolOutcome.BLOCKED
    assert _SCOPE_MARK in result.output
    assert "list_dir, read_file" in result.output

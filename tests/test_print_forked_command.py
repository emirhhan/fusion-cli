"""`-p "/<beceri>"` + `context: fork` (#289): alt ajanda koşar, kimlik `forked-command-…`.

Claude Code headless (Follow subagent messages): istemden başlatılan fork becerisinin
mesajlarında `parent_tool_use_id` `forked-command-` ile başlar; mesajlar beceri bitince toplu
ve sırayla gelir. Agent aracıyla başlayan alt ajanlar çağrının `tool_use` kimliğini taşır.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

from fusion_cli.cli import app as app_module
from fusion_cli.cli import print_run
from fusion_cli.cli.sdk_subagents import FORKED_COMMAND_PREFIX, SubagentForwarder
from fusion_cli.core.events import (
    SubAgentFinished,
    SubAgentStarted,
    ToolExecuted,
    ToolOutcome,
    ToolStarted,
)
from fusion_cli.engines.agent.team_fork import run_forked_turn

runner = CliRunner()


def _skill(tmp_path, *, fork: bool) -> None:
    folder = tmp_path / ".claude" / "skills" / "derle"
    folder.mkdir(parents=True)
    context = "context: fork\n" if fork else ""
    (folder / "SKILL.md").write_text(
        f"---\nname: derle\ndescription: derle\n{context}---\nProjeyi derle.\n", encoding="utf-8"
    )


def _events() -> list[object]:
    return [
        SubAgentStarted(task="Projeyi derle", sub_id="yardimci-1"),
        ToolStarted(
            name="run_shell", args={"command": "make"}, call_id="c1", agent_id="yardimci-1"
        ),
        ToolExecuted(
            name="run_shell",
            args={"command": "make"},
            outcome=ToolOutcome.OK,
            output="tamam",
            call_id="c1",
            agent_id="yardimci-1",
        ),
        SubAgentFinished(tool_calls=1, sub_id="yardimci-1", summary="derlendi"),
    ]


def _run(monkeypatch, tmp_path, *, fork: bool):
    _skill(tmp_path, fork=fork)
    monkeypatch.chdir(tmp_path)
    calls: list[dict[str, object]] = []

    async def _fake(task, config, **kwargs):
        calls.append(kwargs)
        if kwargs.get("turn_runner") is not None:
            for event in _events():
                for sink in kwargs["sinks"]:
                    sink.handle(event)
        return SimpleNamespace(
            final_text="derlendi",
            ok=True,
            stop_reason=None,
            model_calls_made=1,
            hit_step_limit=False,
            messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    args = ["-p", "/derle", "--output-format", "stream-json", "--verbose"]
    return calls, runner.invoke(app_module.app, args)


def _rows(stdout: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in stdout.splitlines() if line.startswith("{")]


def test_fork_becerisi_alt_ajanda_kosar_ve_forked_command_kimligi_tasir(monkeypatch, tmp_path):
    calls, result = _run(monkeypatch, tmp_path, fork=True)
    assert result.exit_code == 0, result.output
    runner_used = calls[0]["turn_runner"]
    assert getattr(runner_used, "func", runner_used) is run_forked_turn
    rows = _rows(result.stdout)
    sub = [row for row in rows if row.get("parent_tool_use_id")]
    assert sub and all(row["parent_tool_use_id"] == "forked-command-derle" for row in sub)
    assert sub[0]["type"] == "user"
    assert any(
        block.get("type") == "tool_use" for row in sub for block in row["message"]["content"]
    )
    assert rows[-1]["type"] == "result"


def test_fork_olmayan_beceri_satir_icinde_kalir(monkeypatch, tmp_path):
    calls, result = _run(monkeypatch, tmp_path, fork=False)
    assert result.exit_code == 0, result.output
    assert calls[0].get("turn_runner") is None
    assert FORKED_COMMAND_PREFIX not in result.stdout


def test_fork_mesajlari_beceri_bitince_toplu_ve_sirayla_gelir():
    written: list[tuple[str, str]] = []
    forwarder = SubagentForwarder(
        assistant=lambda content, parent: written.append(("assistant", parent)),
        user=lambda content, parent: written.append(("user", parent)),
        forward_text=False,
    )
    forwarder.expect_forked_command("derle")
    events = _events()
    for event in events[:-1]:
        forwarder.observe(event)
    assert written == []
    forwarder.observe(events[-1])
    assert [kind for kind, _ in written] == ["user", "assistant", "user"]
    assert {parent for _, parent in written} == {"forked-command-derle"}


def test_baslamayan_fork_kaydi_agent_cagrisini_calmaz():
    written: list[str] = []
    forwarder = SubagentForwarder(
        assistant=lambda content, parent: written.append(parent),
        user=lambda content, parent: written.append(parent),
        forward_text=False,
    )
    forwarder.expect_forked_command("derle")
    forwarder.clear_forked_command()
    forwarder.observe(ToolStarted(name="spawn_agent", args={}, call_id="toolu_1"))
    forwarder.observe(SubAgentStarted(task="iş", sub_id="a-1"))
    assert written == ["toolu_1"]

"""Host kit planından güvenli arka plan render başlangıcı."""

from dataclasses import replace

import pytest

from fusion_cli.core.remotion_browser import RemotionBrowser
from fusion_cli.core.tools import ToolContext, ToolResult
from fusion_cli.tools.remotion_scaffold import scaffold_remotion


async def _context(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    context = ToolContext(root=tmp_path)
    assert (
        await scaffold_remotion(
            {
                "path": "video",
                "composition_id": "Fusion",
                "timeout_s": 10,
                "scenes": [{"id": "intro", "kind": "feature", "duration": 120}],
            },
            context,
        )
    ).ok
    for name in ("tsc", "remotion"):
        binary = tmp_path / "video/node_modules/.bin" / name
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
    browser = tmp_path / "Chrome browser"
    browser.write_text("#!/bin/sh\n")
    browser.chmod(0o755)
    return replace(context, remotion_browser=RemotionBrowser(browser, "chrome-for-testing"))


async def test_launch_uses_immutable_contract_local_binaries_and_job_receipts(
    tmp_path, monkeypatch
):
    from fusion_cli.tools import remotion_render

    context = await _context(tmp_path)
    captured = []

    def launch(args, actual):
        captured.append(args)
        assert actual is context
        return ToolResult("İş başladı: abc")

    monkeypatch.setattr(remotion_render, "run_shell", launch)
    result = await remotion_render.render_remotion({"output": "out/new film.mp4"}, context)
    assert result.ok and "tamamlan" not in result.output
    args = captured[0]
    assert args["background"] is True
    assert args["expected_outputs"] == ["out/new film.mp4"]
    assert args["failure_sources"] == [
        "video/src",
        "video/public",
        "video/package.json",
        "video/tsconfig.json",
    ]
    command = args["command"]
    assert "--strict" in command and " && " in command
    assert "npx" not in command and "--browser-executable" in command
    assert "--chrome-mode=chrome-for-testing" in command and "Fusion" in command


@pytest.mark.parametrize("output", ["../escape.mp4", "/outside.mp4", ".env/x.mp4", "out/a.webm"])
async def test_unsafe_output_never_launches(tmp_path, monkeypatch, output):
    from fusion_cli.tools import remotion_render

    context = await _context(tmp_path)
    monkeypatch.setattr(remotion_render, "run_shell", lambda *args: pytest.fail("Başlatılmamalı"))
    assert not (await remotion_render.render_remotion({"output": output}, context)).ok


@pytest.mark.parametrize("fault", ["contract", "browser", "binary", "kit", "shadow", "output"])
async def test_missing_or_changed_prerequisites_never_launch(tmp_path, monkeypatch, fault):
    from fusion_cli.tools import remotion_render

    context = await _context(tmp_path)
    if fault == "contract":
        context = ToolContext(root=tmp_path)
    elif fault == "browser":
        context = replace(context, remotion_browser=None)
    elif fault == "binary":
        (tmp_path / "video/node_modules/.bin/tsc").unlink()
    elif fault == "kit":
        (tmp_path / "video/src/kit/Timeline.tsx").write_text("changed")
    elif fault == "shadow":
        (tmp_path / "video/src/kit.ts").write_text("shadow")
    else:
        (tmp_path / "out.mp4").write_bytes(b"old")
    monkeypatch.setattr(remotion_render, "run_shell", lambda *args: pytest.fail("Başlatılmamalı"))
    assert not (await remotion_render.render_remotion({"output": "out.mp4"}, context)).ok


async def test_model_browser_override_and_symlink_escape_never_launch(tmp_path, monkeypatch):
    from fusion_cli.tools import remotion_render

    context = await _context(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    (context.root / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(remotion_render, "run_shell", lambda *args: pytest.fail("Başlatılmamalı"))
    assert not (
        await remotion_render.render_remotion(
            {"output": "out.mp4", "browser": "/model/browser"}, context
        )
    ).ok
    assert not (await remotion_render.render_remotion({"output": "escape/a.mp4"}, context)).ok


async def test_job_launch_failure_remains_failure(tmp_path, monkeypatch):
    from fusion_cli.tools import remotion_render

    context = await _context(tmp_path)
    failure = ToolResult.failure("İş başlatılamadı")
    monkeypatch.setattr(remotion_render, "run_shell", lambda *args: failure)
    assert await remotion_render.render_remotion({"output": "out.mp4"}, context) is failure


def test_render_tool_registry_has_only_output_and_mutating_effect():
    from fusion_cli.tools.builtin import build_registry

    tool = build_registry().get("render_remotion")
    assert tool.mutating
    assert set(tool.parameters["properties"]) == {"output"}


def test_render_skill_keeps_host_tool_and_final_verification_inside_existing_budget():
    from fusion_cli.engines.agent.expertise import expertise_hint

    hint = expertise_hint("Remotion ile tanıtım videosu üret")
    assert hint is not None
    assert 'render_remotion(output="out/video.mp4")' in hint
    assert "teslim kanıtı" in hint and "animasyon çalışmıyor demektir." in hint


@pytest.mark.parametrize("fault", ["cancelled", "scope"])
async def test_cancel_or_write_scope_blocks_before_output_directory(tmp_path, monkeypatch, fault):
    from fusion_cli.tools import remotion_render

    context = await _context(tmp_path)
    if fault == "cancelled":
        context.cancelled.set()
    else:
        context = replace(context, write_scope=(tmp_path / "allowed",))
    monkeypatch.setattr(remotion_render, "run_shell", lambda *args: pytest.fail("Başlatılmamalı"))
    assert not (await remotion_render.render_remotion({"output": "blocked/out.mp4"}, context)).ok
    assert not (tmp_path / "blocked").exists()


async def test_cancellation_during_preparation_prevents_job_launch(tmp_path, monkeypatch):
    from fusion_cli.tools import remotion_render

    context = await _context(tmp_path)
    prepare = remotion_render._prepare

    def prepare_then_cancel(args, actual):
        result = prepare(args, actual)
        actual.cancelled.set()
        return result

    monkeypatch.setattr(remotion_render, "_prepare", prepare_then_cancel)
    monkeypatch.setattr(remotion_render, "run_shell", lambda *args: pytest.fail("Başlatılmamalı"))
    assert not (await remotion_render.render_remotion({"output": "out.mp4"}, context)).ok


async def test_strict_project_command_avoids_ts7_positional_config_conflict(tmp_path):
    import shlex

    from fusion_cli.tools.remotion_render import _command

    context = await _context(tmp_path)
    command = _command(
        tmp_path / "video", context.remotion_contract.registered, tmp_path / "new.mp4", context
    )
    strict = shlex.split(command.split(" && ")[1])
    assert "--project" in strict
    assert strict[strict.index("--project") + 1] == str(tmp_path / "video/tsconfig.json")
    assert str(tmp_path / "video/src/index.tsx") not in strict
    assert "--strict" in strict and "--noUnusedLocals" in strict


async def test_changed_project_config_never_weakens_strict_launch(tmp_path, monkeypatch):
    from fusion_cli.tools import remotion_render

    context = await _context(tmp_path)
    (tmp_path / "video/tsconfig.json").write_text('{"compilerOptions":{"strict":false}}')
    monkeypatch.setattr(remotion_render, "run_shell", lambda *args: pytest.fail("Başlatılmamalı"))
    assert not (await remotion_render.render_remotion({"output": "new.mp4"}, context)).ok


async def test_project_config_mutation_invalidates_completed_delivery(tmp_path):
    from fusion_cli.core.evidence import ToolUse
    from fusion_cli.engines.agent.turn_report import build_turn_report
    from fusion_cli.tools import jobs, shell
    from fusion_cli.tools.job_current import snapshot_current_jobs
    from fusion_cli.tools.remotion_render import _prepare

    context = await _context(tmp_path)
    args = _prepare({"output": "new.mp4"}, context)
    args["command"] = "echo new > new.mp4"
    start = shell.run_shell(args, context)
    done = jobs.job_status({"id": start.job_completion.job_id, "wait_s": 10}, context)
    assert done.job_completion.exit_code == 0
    assert "video/tsconfig.json" in done.job_completion.source_scopes
    uses = (
        ToolUse("run_shell", job_completion=start.job_completion),
        ToolUse("job_status", job_completion=done.job_completion),
    )
    (tmp_path / "video/tsconfig.json").write_text('{"compilerOptions":{"strict":false}}')
    report = build_turn_report((), uses, None, current_jobs=snapshot_current_jobs(tmp_path, uses))
    assert report.blocks_success

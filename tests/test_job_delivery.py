"""Başlatma başarı değildir; eski çıktı başarısız denemeyi örtemez."""

from __future__ import annotations

from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.job_evidence import ArtifactReceipt, JobCompletion, JobPhase
from fusion_cli.core.repair_ledger import SourceFingerprint
from fusion_cli.engines.agent.turn_report import build_turn_report


def use(phase: JobPhase, exit_code: int | None = None, outputs=(), job="one") -> ToolUse:
    return ToolUse(
        "run_shell" if phase is JobPhase.STARTED else "job_status",
        mutating=phase is JobPhase.STARTED,
        job_completion=JobCompletion(
            job, "npx remotion render Main out.mp4", phase, exit_code, outputs=outputs
        ),
    )


def write() -> ToolUse:
    return ToolUse("write_file", mutating=True, arguments={"path": "src/a.tsx"})


def test_launch_and_pending_block_completion_without_changed_files() -> None:
    report = build_turn_report((), (use(JobPhase.STARTED), use(JobPhase.RUNNING)), None)
    assert report.blocks_success and report.is_verified is False
    assert "sürüyor" in report.render().lower()


def test_completed_real_exit_joins_launch_command_and_deduplicates_poll() -> None:
    done = use(JobPhase.COMPLETED, 0)
    report = build_turn_report(("src/a.tsx",), (write(), use(JobPhase.STARTED), done, done), None)
    assert len(report.command_runs) == 1
    assert report.command_runs[0].exit_code == 0
    assert not report.blocks_success


def test_launch_before_mutation_cannot_verify_new_source_at_completion() -> None:
    report = build_turn_report(
        ("src/a.tsx",), (use(JobPhase.STARTED), write(), use(JobPhase.COMPLETED, 0)), None
    )
    assert report.is_verified is False
    assert not report.command_runs[0].after_last_mutation


def test_failed_new_job_blocks_even_with_existing_old_mp4() -> None:
    stale = ArtifactReceipt("out.mp4", "old", "old")
    report = build_turn_report(
        (), (use(JobPhase.STARTED), use(JobPhase.COMPLETED, 1, (stale,))), None
    )
    assert report.blocks_success and report.is_verified is False
    assert "çıkış 1" in report.render()


def test_missing_or_unchanged_expected_output_is_unverified_not_visual_success() -> None:
    for receipt in (
        ArtifactReceipt("out.mp4", None, None),
        ArtifactReceipt("out.mp4", "old", "old"),
    ):
        report = build_turn_report(
            (), (use(JobPhase.STARTED), use(JobPhase.COMPLETED, 0, (receipt,))), None
        )
        assert report.blocks_success and report.is_verified is False


def test_source_hash_changed_during_execution_invalidates_delivery() -> None:
    item = JobCompletion(
        "one",
        "render",
        JobPhase.COMPLETED,
        0,
        (SourceFingerprint("a.tsx", "old"),),
        (SourceFingerprint("a.tsx", "new"),),
    )
    report = build_turn_report(
        (), (use(JobPhase.STARTED), ToolUse("job_status", job_completion=item)), None
    )
    assert report.blocks_success


def test_fresh_successful_retry_resolves_only_same_command_output_scope() -> None:
    old = use(JobPhase.COMPLETED, 1, (ArtifactReceipt("out.mp4", "old", "old"),))
    new = use(JobPhase.COMPLETED, 0, (ArtifactReceipt("out.mp4", "old", "new"),), job="two")
    launch_outputs = (ArtifactReceipt("out.mp4", "old", None),)
    report = build_turn_report(
        (),
        (
            use(JobPhase.STARTED, outputs=launch_outputs),
            old,
            use(JobPhase.STARTED, outputs=launch_outputs, job="two"),
            new,
        ),
        None,
    )
    assert not report.blocks_success
    unrelated = JobCompletion("other", "unrelated", JobPhase.COMPLETED, 1)
    report = build_turn_report(
        (),
        (
            ToolUse("run_shell", job_completion=unrelated),
            use(JobPhase.STARTED, outputs=launch_outputs, job="two"),
            new,
        ),
        None,
    )
    assert report.blocks_success


def test_actual_jobs_capture_missing_refreshed_and_changed_source(tmp_path) -> None:
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import jobs, shell

    (tmp_path / "a.tsx").write_text("source")
    context = ToolContext(root=tmp_path)
    started = shell.run_shell(
        {
            "command": "echo new > out.mp4",
            "background": True,
            "failure_check": "layout",
            "failure_sources": ["a.tsx"],
            "expected_outputs": ["out.mp4"],
        },
        context,
    )
    assert started.job_completion.phase is JobPhase.STARTED
    result = jobs.job_status({"id": started.job_completion.job_id, "wait_s": 10}, context)
    assert result.job_completion.exit_code == 0
    assert result.job_completion.outputs[0].is_refreshed
    assert result.job_completion.sources_before == result.job_completion.sources_after
    (tmp_path / "a.tsx").write_text("changed")
    later = jobs.job_status({"id": started.job_completion.job_id}, context)
    # Tamamlanma anındaki ölçüm daha sonraki disk değişikliğiyle yeniden yazılmaz.
    assert later.job_completion == result.job_completion


def test_directory_membership_addition_invalidates_completed_source_manifest(tmp_path) -> None:
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import jobs, shell

    folder = tmp_path / "src"
    folder.mkdir()
    (folder / "a.tsx").write_text("source")
    context = ToolContext(root=tmp_path)
    started = shell.run_shell(
        {
            "command": "while [ ! -f release ]; do sleep 0.01; done",
            "background": True,
            "failure_check": "layout",
            "failure_sources": ["src"],
        },
        context,
    )
    (folder / "new.tsx").write_text("new member")
    (tmp_path / "release").touch()
    result = jobs.job_status({"id": started.job_completion.job_id, "wait_s": 10}, context)
    assert result.job_completion.sources_before != result.job_completion.sources_after
    assert {item.path for item in result.job_completion.sources_after} == {
        "src/a.tsx",
        "src/new.tsx",
    }


def test_missing_output_cannot_become_fresh_by_later_unrelated_write(tmp_path) -> None:
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import jobs, shell

    context = ToolContext(root=tmp_path)
    started = shell.run_shell(
        {"command": "true", "background": True, "expected_outputs": ["out.mp4"]}, context
    )
    first = jobs.job_status({"id": started.job_completion.job_id, "wait_s": 10}, context)
    assert first.job_completion.outputs[0].after_hash is None
    (tmp_path / "out.mp4").write_text("unrelated later output")
    later = jobs.job_status({"id": started.job_completion.job_id}, context)
    assert later.job_completion.outputs[0].after_hash is None
    assert later.job_completion == first.job_completion


def test_unrelated_write_before_first_poll_does_not_rewrite_completion_receipt(tmp_path) -> None:
    import time

    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools import jobs, shell

    context = ToolContext(root=tmp_path)
    started = shell.run_shell(
        {"command": "true", "background": True, "expected_outputs": ["out.mp4"]}, context
    )
    job_id = started.job_completion.job_id
    deadline = time.monotonic() + 10
    while jobs._read_exit(tmp_path / jobs.JOBS_DIR, job_id) is None:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    (tmp_path / "out.mp4").write_text("written after command finished, before first poll")
    result = jobs.job_status({"id": job_id}, context)
    assert result.job_completion.outputs[0].after_hash is None


async def test_real_agent_launch_only_is_not_success_and_poll_is_not_mutation(
    monkeypatch, tmp_path
) -> None:
    from fusion_cli.core.events import ToolOutcome
    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent import loop

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import TAM_CEVAP, _deps, _kur

    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("run_shell", command="render", background=True)]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )

    async def execute(*args, **kwargs):
        return ToolResult(
            "başladı", job_completion=JobCompletion("one", "render", JobPhase.STARTED)
        ), ToolOutcome.OK

    monkeypatch.setattr(loop, "_execute", execute)
    result = await loop.run_agent(
        "video üret", _deps(tmp_path, RecordingSink()), self_review=False, verify=False
    )
    assert not result.ok and "sürüyor" in result.final_text
    state = loop._State()
    loop._note_tool_use(
        state,
        "job_status",
        None,
        ok=True,
        is_observation=True,
        job_completion=JobCompletion("one", "render", JobPhase.COMPLETED, 0),
    )
    assert not state.tool_uses[0].mutating


async def test_real_agent_completed_background_exit_reaches_report(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from fusion_cli.engines.agent import loop
    from fusion_cli.tools import jobs

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_turn_budget import TAM_CEVAP, _deps, _kur

    monkeypatch.setattr(
        jobs, "uuid", SimpleNamespace(uuid4=lambda: SimpleNamespace(hex="abcdef12"))
    )
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        tool_call(
                            "run_shell",
                            command="echo fixture > out.mp4",
                            background=True,
                            expected_outputs=["out.mp4"],
                        )
                    ]
                ),
                model_result(tool_calls=[tool_call("job_status", id="abcdef12", wait_s=10)]),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    result = await loop.run_agent(
        "video üret", _deps(tmp_path, RecordingSink()), self_review=False, verify=False
    )
    assert result.ok
    assert "tamamlandı (çıkış 0)" in result.final_text
    poll = next(item for item in result.tool_uses if item.name == "job_status")
    assert not poll.mutating and poll.job_completion.exit_code == 0
    assert poll.job_completion.outputs[0].is_refreshed

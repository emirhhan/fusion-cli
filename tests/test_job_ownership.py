"""Job stop yalnız doğrulanmış süreç başlangıcı ve owner kapsamında çalışır."""

import os
from contextlib import suppress

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import jobs, shell


def test_legacy_pid_without_identity_cannot_kill_recycled_process(tmp_path, monkeypatch):
    folder = tmp_path / jobs.JOBS_DIR
    folder.mkdir(parents=True)
    (folder / "12345678.cmd").write_text("old command")
    (folder / "12345678.pid").write_text("12345")
    killed = []
    monkeypatch.setattr(os, "killpg", lambda *args: killed.append(args))
    result = jobs.job_status({"id": "12345678", "stop": True}, ToolContext(root=tmp_path))
    assert not result.ok
    assert not killed
    assert not (folder / "12345678.exit").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX identity fixture")
def test_other_context_cannot_stop_owned_job(tmp_path):
    owner = ToolContext(root=tmp_path)
    other = ToolContext(root=tmp_path)
    started = shell.run_shell({"command": "sleep 30", "background": True}, owner)
    job_id = started.job_completion.job_id
    try:
        rejected = jobs.job_status({"id": job_id, "stop": True}, other)
        assert not rejected.ok
        assert not (tmp_path / jobs.JOBS_DIR / f"{job_id}.exit").exists()
    finally:
        jobs.job_status({"id": job_id, "stop": True}, owner)


@pytest.mark.skipif(os.name == "nt", reason="POSIX identity fixture")
def test_reopened_matching_scope_can_stop_and_reap_job(tmp_path):
    owner = ToolContext(root=tmp_path)
    started = shell.run_shell({"command": "sleep 30", "background": True}, owner)
    job_id = started.job_completion.job_id
    pid = int((tmp_path / jobs.JOBS_DIR / f"{job_id}.pid").read_text())
    resumed = ToolContext(root=tmp_path, job_scope=owner.job_scope)
    try:
        stopped = jobs.job_status({"id": job_id, "stop": True}, resumed)
        assert stopped.ok, stopped.output
        with pytest.raises(ProcessLookupError):
            os.killpg(pid, 0)
        assert jobs.job_status({"id": job_id, "stop": True}, resumed).ok
    finally:
        jobs.job_status({"id": job_id, "stop": True}, owner)


@pytest.mark.skipif(os.name == "nt", reason="POSIX identity fixture")
def test_changed_process_identity_is_never_signalled(tmp_path, monkeypatch):
    from fusion_cli.tools import job_owner

    owner = ToolContext(root=tmp_path)
    started = shell.run_shell({"command": "sleep 30", "background": True}, owner)
    job_id = started.job_completion.job_id
    try:
        with monkeypatch.context() as patch:
            patch.setattr(job_owner, "process_identity", lambda *args: "different-start")
            calls = []
            patch.setattr(
                jobs, "terminate_process_tree", lambda *args, **kwargs: calls.append(args)
            )
            stopped = jobs.job_status({"id": job_id, "stop": True}, owner)
            assert not stopped.ok
            assert not calls
    finally:
        jobs.job_status({"id": job_id, "stop": True}, owner)


def test_child_inherits_job_owner_scope(tmp_path):
    from fusion_cli.engines.agent.team_scope import derive_sub_context

    parent = ToolContext(root=tmp_path)
    assert derive_sub_context(parent).job_scope == parent.job_scope


@pytest.mark.skipif(os.name == "nt", reason="POSIX launch failure fixture")
def test_failed_owner_registration_cleans_spawned_process(tmp_path, monkeypatch):
    import signal
    import subprocess

    real_popen = subprocess.Popen
    spawned = []

    def capture(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        spawned.append(process)
        return process

    monkeypatch.setattr(jobs.subprocess, "Popen", capture)
    monkeypatch.setattr(jobs, "save_owner", lambda *args: (_ for _ in ()).throw(OSError("disk")))
    try:
        result = shell.run_shell(
            {"command": "sleep 30", "background": True}, ToolContext(root=tmp_path)
        )
        assert not result.ok
        with pytest.raises(ProcessLookupError):
            os.killpg(spawned[0].pid, 0)
    finally:
        for process in spawned:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)

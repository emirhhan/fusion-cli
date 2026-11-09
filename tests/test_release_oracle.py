"""Offline production inspectors derive results from candidate files, not PASS JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion
from scripts import release_oracle


def _candidates(tmp_path: Path, monkeypatch, content: str) -> Path:
    task = EvalTask(
        "one",
        "change only product",
        SuccessCriterion(
            CriterionKind.EXIT_CODE,
            expected_exit_code=0,
            command=(
                'python -c "from pathlib import Path; '
                "assert Path('product.txt').read_text()=='good'\""
            ),
        ),
        setup={"product.txt": "seed"},
    )
    monkeypatch.setattr(release_oracle, "load_tasks", lambda path: (task,))
    workspaces = tmp_path / "candidates"
    for index in range(1, 4):
        candidate = workspaces / "one" / f"run-{index:02d}"
        candidate.mkdir(parents=True)
        (candidate / "product.txt").write_text(content)
        (candidate / "report.json").write_text('{"passed": true, "independent": true}')
    return workspaces


@pytest.mark.parametrize("content,expected", [("good", "passed"), ("wrong", "failed")])
async def test_oracle_reexecutes_trusted_acceptance(tmp_path, monkeypatch, content, expected):
    root = _candidates(tmp_path, monkeypatch, content)
    rows = await release_oracle.inspect_workspaces(root, repeat=3)
    assert len(rows) == 3
    assert {row["outcome"] for row in rows} == {expected}
    assert all(len(row["candidate_digest"]) == 64 for row in rows)


async def test_oracle_missing_or_symlinked_workspace_is_not_pass(tmp_path, monkeypatch):
    root = _candidates(tmp_path, monkeypatch, "good")
    (root / "one/run-03/product.txt").unlink()
    (root / "one/run-03/product.txt").symlink_to(root / "one/run-01/product.txt")
    with pytest.raises(Exception, match="bağlantı"):
        await release_oracle.inspect_workspaces(root, repeat=3)


def test_receipt_is_explicitly_evidence_only_and_cannot_overwrite(tmp_path, monkeypatch):
    root = _candidates(tmp_path, monkeypatch, "good")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "app.dmg").write_bytes(b"candidate-package")
    output = tmp_path / "receipt.json"
    args = [
        "--workspaces",
        str(root),
        "--artifacts",
        str(artifacts),
        "--version",
        "1.2.3",
        "--commit",
        "a" * 40,
        "--out",
        str(output),
    ]
    assert release_oracle.main(args) == 0
    receipt = json.loads(output.read_text())
    assert receipt["status"] == "evidence_only" and receipt["claimsReady"] is False
    assert "executed_packaged_artifact_identity" in receipt["unsatisfied_prerequisites"]
    assert receipt["binding"]["version"] == "1.2.3"
    with pytest.raises(FileExistsError):
        release_oracle.main(args)


async def test_unavailable_oracle_is_unknown(tmp_path, monkeypatch):
    root = _candidates(tmp_path, monkeypatch, "good")

    async def unavailable(self, task, workspace, acceptance):
        return -2

    monkeypatch.setattr(release_oracle.AgentTaskExecutor, "_exit_code", unavailable)
    rows = await release_oracle.inspect_workspaces(root, repeat=3)
    assert {row["outcome"] for row in rows} == {"unknown"}


async def test_candidate_mutation_during_inspection_is_rejected(tmp_path, monkeypatch):
    root = _candidates(tmp_path, monkeypatch, "good")
    original = release_oracle.AgentTaskExecutor.run_sample

    async def mutate(self, task, *, sample_index):
        execution = await original(self, task, sample_index=sample_index)
        (root / "one/run-01/product.txt").write_text("changed-after-inspection")
        return execution

    monkeypatch.setattr(release_oracle.AgentTaskExecutor, "run_sample", mutate)
    with pytest.raises(ValueError, match="değişti"):
        await release_oracle.inspect_workspaces(root, repeat=3)


async def test_isolated_oracle_binds_stable_workspace_after_private_tmp(tmp_path, monkeypatch):
    import shlex

    from evals.acceptance_command import AcceptanceCommand

    from fusion_cli.core.clock import SystemClock

    captured = []

    async def capture(self, task, workspace, acceptance):
        captured.extend(shlex.split(acceptance.command))
        return 0

    monkeypatch.setattr(release_oracle.shutil, "which", lambda name: "/usr/bin/bwrap")
    monkeypatch.setattr(release_oracle.AgentTaskExecutor, "_exit_code", capture)
    executor = release_oracle.IsolatedOracleExecutor(
        release_oracle._ReplayCandidate(tmp_path),
        workspace_root=tmp_path,
        clock=SystemClock(),
    )
    task = EvalTask(
        "one",
        "task",
        SuccessCriterion(CriterionKind.EXIT_CODE, expected_exit_code=0, command="true"),
    )
    await executor._exit_code(task, tmp_path, AcceptanceCommand("true"))
    assert captured.index("--tmpfs") < captured.index("--bind")
    assert captured[captured.index("--bind") + 1 : captured.index("--bind") + 3] == [
        str(tmp_path),
        "/workspace",
    ]
    assert captured[captured.index("--chdir") + 1] == "/workspace"
    assert {"--unshare-all", "--clearenv", "--cap-drop"} <= set(captured)


@pytest.mark.parametrize(
    "code,expected",
    [
        (
            "async def smoke(client):\n"
            "    await client.list_tools()\n"
            "    await client.call_tool('ping', {})\n",
            "passed",
        ),
        (
            "print('import log')\n"
            "async def smoke(client):\n"
            "    await client.list_tools()\n"
            "    print('tools listed')\n"
            "    await client.call_tool('ping', {})\n",
            "passed",
        ),
        ("raise SystemExit(0)\n", "failed"),
        ("import os\nos._exit(0)\n", "failed"),
    ],
)
async def test_mcp_oracle_witness_lives_outside_candidate_process(
    tmp_path, monkeypatch, code, expected
):
    from evals.loader import load_tasks

    task = next(
        task
        for task in load_tasks(release_oracle.ROOT / "evals/suite/production.yaml")
        if task.id == "mcp-stdio-listele-cagir"
    )
    monkeypatch.setattr(release_oracle, "load_tasks", lambda path: (task,))
    for index in range(1, 4):
        root = tmp_path / task.id / f"run-{index:02d}"
        root.mkdir(parents=True)
        (root / "mcp_candidate.py").write_text(code)
    rows = await release_oracle.inspect_workspaces(tmp_path, repeat=3)
    assert {row["outcome"] for row in rows} == {expected}


async def test_candidate_json_module_cannot_exit_before_trusted_json_assertions(
    tmp_path, monkeypatch
):
    from evals.loader import load_tasks

    task = next(
        task
        for task in load_tasks(release_oracle.ROOT / "evals/suite/production.yaml")
        if task.id == "json-dosya-izolasyonu"
    )
    monkeypatch.setattr(release_oracle, "load_tasks", lambda path: (task,))
    for index in range(1, 4):
        root = tmp_path / task.id / f"run-{index:02d}"
        root.mkdir(parents=True)
        (root / "conversation-a.json").write_text('{"status":"wrong"}')
        (root / "conversation-b.json").write_text('{"status":"wrong"}')
        (root / "json.py").write_text("import os\nos._exit(0)\n")
    rows = await release_oracle.inspect_workspaces(tmp_path, repeat=3)
    assert {row["outcome"] for row in rows} == {"failed"}

#!/usr/bin/env python3
"""Reinspect saved production workspaces with the existing trusted eval executor.

This offline producer never invokes an actor/provider or imports a candidate report.
Its receipt is diagnostic evidence, not proof of protected provenance or packaged
execution. Publication remains blocked until those trust boundaries are integrated.
Run from the checkout with PYTHONPATH=src:.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shlex
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from evals.acceptance_command import AcceptanceCommand
from evals.executor import (
    EXIT_VERIFICATION_TIMEOUT,
    EXIT_VERIFICATION_UNAVAILABLE,
    AgentRunObservation,
    AgentTaskExecutor,
    _snapshot,
)
from evals.loader import load_tasks
from evals.metrics import score_task
from evals.profiles import _digest_entries, _scorer_entries, _source_entries
from evals.tasks import EvalTask
from scripts.release_manifest import ROOT, collect_artifacts, sha256_file

from fusion_cli.core.clock import SystemClock


class _ReplayCandidate:
    """Copy candidate bytes only; the executor owns seed/acceptance/evaluation."""

    def __init__(self, source: Path) -> None:
        self.source = source
        self.snapshot = _snapshot(source)

    async def run(self, request: str, *, root: Path, **kwargs: object) -> AgentRunObservation:
        await asyncio.to_thread(self._copy, root)
        return AgentRunObservation("", model_calls=0, claimed_success=False)

    def _copy(self, root: Path) -> None:
        if _snapshot(self.source) != self.snapshot:
            raise ValueError("Oracle girdisi kopyalama öncesinde değişti.")
        for path in root.iterdir():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        shutil.copytree(self.source, root, dirs_exist_ok=True)
        if _snapshot(root) != self.snapshot or _snapshot(self.source) != self.snapshot:
            raise ValueError("Oracle girdisi kopyalama sırasında değişti.")


class IsolatedOracleExecutor(AgentTaskExecutor):
    """Candidate acceptance code cannot reach host processes/files/credentials.

    The host orchestrator owns exit status and evidence. The namespace contains
    only read-only host paths, a writable clean workspace and private /tmp/proc.
    """

    async def _exit_code(
        self, task: EvalTask, workspace: Path, acceptance: AcceptanceCommand
    ) -> int | None:
        sandbox = shutil.which("bwrap")
        if sandbox is None:
            raise ValueError("Bağımsız verifier için Linux bubblewrap zorunlu.")
        if acceptance.command is None:
            return await super()._exit_code(task, workspace, acceptance)
        command = [
            sandbox,
            "--die-with-parent",
            "--unshare-all",
            "--ro-bind",
            "/",
            "/",
            "--tmpfs",
            "/tmp",
            "--dir",
            "/workspace",
            "--bind",
            str(workspace),
            "/workspace",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--cap-drop",
            "ALL",
            "--clearenv",
            "--setenv",
            "PATH",
            os.pathsep.join((str(Path(sys.executable).parent), "/usr/bin", "/bin")),
            "--setenv",
            "PYTHONPATH",
            os.pathsep.join((str(ROOT), str(ROOT / "src"))),
            "--setenv",
            "PYTHONUTF8",
            "1",
            "--setenv",
            "HOME",
            "/tmp",
            "--setenv",
            "PYTHONOPTIMIZE",
            "0",
            "--setenv",
            "PYTHONSAFEPATH",
            "1",
            "--chdir",
            "/workspace",
            "/bin/sh",
            "-c",
            acceptance.command,
        ]
        return await super()._exit_code(
            task, workspace, replace(acceptance, command=shlex.join(command))
        )


class MacIsolatedOracleExecutor(AgentTaskExecutor):
    """Use the existing mandatory macOS sandbox for trusted feedback inspection."""

    async def _exit_code(
        self, task: EvalTask, workspace: Path, acceptance: AcceptanceCommand
    ) -> int | None:
        from fusion_cli.core.sandbox_policy import SandboxPolicy
        from fusion_cli.core.shell_sandbox import plan_shell_sandbox

        policy = SandboxPolicy(
            fail_if_unavailable=True,
            allow_unsandboxed=False,
            hide_secret_env=True,
            allow_localhost=False,
        )
        plan = plan_shell_sandbox("write_root", (workspace,), policy=policy)
        if sys.platform != "darwin" or not plan.is_active or plan.refused:
            raise ValueError("Trusted feedback requires the mandatory macOS sandbox.")
        if acceptance.command is None:
            return await super()._exit_code(task, workspace, acceptance)
        command = shlex.join([*plan.prefix, "/bin/sh", "-c", acceptance.command])
        return await super()._exit_code(task, workspace, replace(acceptance, command=command))


async def inspect_workspaces(
    workspaces: Path, *, repeat: int, isolated: bool = False
) -> list[dict[str, object]]:
    """Fresh seeded clean copies preserve the executor's frozen acceptance inputs."""
    if repeat < 3:
        raise ValueError("Production oracle en az üç tekrar gerektirir.")
    tasks = load_tasks(ROOT / "evals/suite/production.yaml")
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="fusion-release-oracle-") as directory:
        for task in tasks:
            for index in range(1, repeat + 1):
                candidate = workspaces / task.id / f"run-{index:02d}"
                if not candidate.is_dir() or any(
                    path.is_symlink()
                    for path in [
                        workspaces,
                        candidate.parent,
                        candidate,
                    ]
                ):
                    raise ValueError(f"Oracle çalışma dizini eksik/bağlantı: {task.id}/{index}")
                runner = _ReplayCandidate(candidate)
                executor_type = IsolatedOracleExecutor if isolated else AgentTaskExecutor
                executor = executor_type(
                    runner, workspace_root=Path(directory), clock=SystemClock()
                )
                execution = await executor.run_sample(task, sample_index=index)
                result = score_task(task, execution)
                if _snapshot(candidate) != runner.snapshot:
                    raise ValueError("Oracle girdisi denetim sırasında değişti.")
                outcome = "passed" if result.success else "failed"
                if execution.exit_code in (
                    None,
                    EXIT_VERIFICATION_TIMEOUT,
                    EXIT_VERIFICATION_UNAVAILABLE,
                ):
                    outcome = "unknown"
                results.append(
                    {
                        "task_id": task.id,
                        "repeat": index,
                        "candidate_digest": _digest_entries(runner.snapshot),
                        "exit_code": execution.exit_code,
                        "outcome": outcome,
                    }
                )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspaces", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    workspaces = args.workspaces.resolve()
    output = args.out.resolve()
    if output.is_relative_to(workspaces) or output.is_relative_to(args.artifacts.resolve()):
        parser.error("Oracle çıktısı aday çalışma ve artefakt kökleri dışında olmalı.")
    artifacts = collect_artifacts(args.artifacts)
    suite = ROOT / "evals/suite/production.yaml"
    split = sha256_file(suite)
    source = _digest_entries(_source_entries(ROOT))
    scorer = _digest_entries(_scorer_entries(ROOT))
    results = asyncio.run(inspect_workspaces(workspaces, repeat=args.repeat))
    if (
        source != _digest_entries(_source_entries(ROOT))
        or scorer != _digest_entries(_scorer_entries(ROOT))
        or artifacts != collect_artifacts(args.artifacts)
        or split != sha256_file(suite)
    ):
        raise SystemExit("Oracle koşusu sırasında kaynak/puanlayıcı/paket değişti.")
    payload = {
        "schema": 1,
        "status": "evidence_only",
        "claimsReady": False,
        "binding": {
            "version": args.version,
            "measured_at": time.time(),
            "split_digest": split,
            "repeat": args.repeat,
            "task_ids": sorted({str(item["task_id"]) for item in results}),
            "commit": args.commit,
            "artifacts": artifacts,
            "source_digest": source,
            "scorer_digest": scorer,
        },
        "results": results,
        "unsatisfied_prerequisites": [
            "protected_actor_inspector_publication_handoff",
            "executed_packaged_artifact_identity",
            "approved_observed_model_and_effective_config",
        ],
    }
    # Exclusive creation prevents accidentally replacing a prior receipt. Read-only
    # mode is convenience, not authentication: an owner can still replace the file.
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444), "w") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")
    return 0 if all(item["outcome"] == "passed" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

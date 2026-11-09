"""Bound trusted feedback for the existing CommandVerifier; not release authority."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.feedback_binding import (
    INSPECTOR_COMMAND,
    assert_interpreter_location,
    assert_protected_path,
    assert_source_locations,
    digest,
    render_wrapper,
)
from evals.loader import load_tasks
from evals.metrics import score_task
from evals.profiles import _digest_entries, _scorer_entries, _source_entries
from scripts.release_manifest import ROOT
from scripts.release_oracle import MacIsolatedOracleExecutor, _ReplayCandidate

from fusion_cli.core.clock import SystemClock
from fusion_cli.core.redaction import redact


def _safe_path(prefix: Path) -> str:
    return os.pathsep.join(
        dict.fromkeys(
            (
                str(prefix),
                str(Path(sys.executable).absolute().parent),
                "/usr/bin",
                "/bin",
                "/usr/sbin",
                "/sbin",
            )
        )
    )


def _validate(binding: Path, expected_digest: str) -> dict[str, Any]:
    if digest(binding) != expected_digest:
        raise ValueError("Inspector binding bytes changed.")
    raw: dict[str, Any] = json.loads(binding.read_text())
    root = Path(raw["root"])
    assert_interpreter_location(Path(raw["python"]), root)
    assert_source_locations(Path(raw["repo"]), Path(raw["profile"]), root)
    if raw.get("command") != INSPECTOR_COMMAND:
        raise ValueError("Inspector command is not the exact fixed route.")
    assert_protected_path(binding, root)
    wrapper = Path(raw["wrapper"])
    assert_protected_path(wrapper, root)
    if wrapper.read_bytes() != render_wrapper(
        binding, expected_digest, Path(raw["python"]), Path(raw["repo"])
    ):
        raise ValueError("Inspector wrapper bytes changed.")
    if str(ROOT.resolve()) != raw["repo"] or digest(Path(raw["python"])) != raw["python_sha256"]:
        raise ValueError("Trusted inspector source/interpreter binding changed.")
    venv_config = Path(raw["python"]).parent.parent / "pyvenv.cfg"
    observed_venv = digest(venv_config) if venv_config.is_file() else None
    if observed_venv != raw["pyvenv_sha256"]:
        raise ValueError("Trusted interpreter environment changed.")
    if str(Path(raw["python"]).resolve()) != raw["python_realpath"]:
        raise ValueError("Trusted interpreter target changed.")
    if digest(Path(raw["profile"])) != raw["profile_sha256"]:
        raise ValueError("Inspector profile binding changed.")
    if _digest_entries(_source_entries(ROOT)) != raw["source_digest"]:
        raise ValueError("Inspector source binding changed.")
    if _digest_entries(_scorer_entries(ROOT)) != raw["scorer_digest"]:
        raise ValueError("Inspector scorer binding changed.")
    if digest(ROOT / "evals/suite/production.yaml") != raw["suite_sha256"]:
        raise ValueError("Inspector suite binding changed.")
    return raw


@dataclass(frozen=True)
class FeedbackControl:
    wrapper: Path
    binding: Path
    binding_sha256: str
    wrapper_sha256: str

    @property
    def environment(self) -> dict[str, str]:
        return {
            "PATH": _safe_path(self.wrapper.parent),
            "FUSION_RELEASE_INSPECTOR": str(self.wrapper),
            "FUSION_RELEASE_INSPECTOR_SHA256": self.wrapper_sha256,
            "FUSION_RELEASE_INSPECTOR_BINDING": str(self.binding),
            "FUSION_RELEASE_INSPECTOR_BINDING_SHA256": self.binding_sha256,
        }

    def assert_unchanged(self) -> None:
        if digest(self.wrapper) != self.wrapper_sha256:
            raise ValueError("Inspector wrapper bytes changed.")
        _validate(self.binding, self.binding_sha256)

    def manifest(self) -> dict[str, str]:
        raw = _validate(self.binding, self.binding_sha256)
        return {
            "command": INSPECTOR_COMMAND,
            "task_id": raw["task_id"],
            "root": raw["root"],
            "wrapper_sha256": self.wrapper_sha256,
            "binding_sha256": self.binding_sha256,
            "python_sha256": raw["python_sha256"],
            "profile_sha256": raw["profile_sha256"],
            "source_digest": raw["source_digest"],
            "scorer_digest": raw["scorer_digest"],
        }


def prepare_feedback(host: Path, root: Path, task_id: str, profile: Path) -> FeedbackControl:
    root, host, profile = root.resolve(), host.resolve(), profile.resolve()
    assert_source_locations(ROOT.resolve(), profile, root)
    host.mkdir(parents=True, exist_ok=False)
    wrapper, binding = host / INSPECTOR_COMMAND, host / "inspector-binding.json"
    python = Path(sys.executable).absolute()
    venv_config = python.parent.parent / "pyvenv.cfg"
    raw = {
        "pyvenv_sha256": digest(venv_config) if venv_config.is_file() else None,
        "schema": 1,
        "command": INSPECTOR_COMMAND,
        "root": str(root),
        "task_id": task_id,
        "repo": str(ROOT.resolve()),
        "wrapper": str(wrapper),
        "python": str(python),
        "python_realpath": str(python.resolve()),
        "python_sha256": digest(python),
        "profile": str(profile),
        "profile_sha256": digest(profile),
        "source_digest": _digest_entries(_source_entries(ROOT)),
        "scorer_digest": _digest_entries(_scorer_entries(ROOT)),
        "suite_sha256": digest(ROOT / "evals/suite/production.yaml"),
    }
    binding.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    binding.chmod(0o444)
    binding_digest = digest(binding)
    wrapper.write_bytes(render_wrapper(binding, binding_digest, python, ROOT.resolve()))
    wrapper.chmod(0o555)
    control = FeedbackControl(wrapper, binding, binding_digest, digest(wrapper))
    control.assert_unchanged()
    return control


def _check_cwd(root: Path) -> None:
    if Path.cwd().resolve() != root or root.is_symlink():
        raise ValueError("Inspector CWD differs from its fixed candidate root.")


async def _inspect(raw: dict[str, Any]) -> bool:
    root = Path(raw["root"])
    _check_cwd(root)
    task = next(
        (
            task
            for task in load_tasks(ROOT / "evals/suite/production.yaml")
            if task.id == raw["task_id"]
        ),
        None,
    )
    if task is None:
        raise ValueError("Inspector task identity is unknown.")
    with tempfile.TemporaryDirectory(prefix="fusion-feedback-home-") as directory:
        # The wrapper inherits the core's environment, so clear it BEFORE any
        # candidate callback can execute. Source/interpreter paths are literals.
        safe = {
            "PATH": os.pathsep.join((str(Path(raw["python"]).parent), "/usr/bin", "/bin")),
            "HOME": directory,
            "USERPROFILE": directory,
            "PYTHONUTF8": "1",
            "PYTHONOPTIMIZE": "0",
        }
        os.environ.clear()
        os.environ.update(safe)
        runner = _ReplayCandidate(root)
        executor = MacIsolatedOracleExecutor(
            runner, workspace_root=Path(directory) / "work", clock=SystemClock()
        )
        execution = await executor.run_sample(task, sample_index=1)
        evidence = Path(directory) / "work" / task.id / "run-01"
        for name in ("_acceptance.stdout.txt", "_acceptance.stderr.txt"):
            path = evidence / name
            if path.is_file():
                output = path.read_text()[-8192:]
                if output:
                    print(redact(output), file=sys.stderr)
        if _ReplayCandidate(root).snapshot != runner.snapshot:
            raise ValueError("Candidate changed during fixed inspector execution.")
        return score_task(task, execution).success


def run_bound(binding_path: str, binding_sha256: str) -> int:
    raw = _validate(Path(binding_path), binding_sha256)
    passed = asyncio.run(_inspect(raw))
    _validate(Path(binding_path), binding_sha256)
    return 0 if passed else 1

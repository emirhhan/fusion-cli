#!/usr/bin/env python3
"""Run the exact frozen artifact via the existing live driver; no oracle/PASS claim.

This stage may call the configured provider ONLY when explicitly executed. The
separate verifier stage re-inspects its output in a fresh CI environment.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from evals.executor import _snapshot, _write_seed_file
from evals.live_drive import drive
from evals.loader import load_tasks
from evals.profiles import _digest_entries, _scorer_entries, _source_entries
from scripts.release_feedback import FeedbackControl, prepare_feedback
from scripts.release_manifest import ROOT, sha256_file
from scripts.release_runtime import extract_runtime, verify_runtime_files

from fusion_cli.core.shell_sandbox import temporary_roots


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")
    temporary.replace(path)


def _checkpoint(out: Path, payload: dict[str, Any], status: str) -> None:
    _atomic_json(
        out / "observations.partial.json",
        {
            **payload,
            "status": status,
            "acceptance_eligible": False,
        },
    )


def _assert_config_unchanged(config: Path, source: Path, expected_sha256: str) -> None:
    if sha256_file(config) != expected_sha256 or sha256_file(source) != expected_sha256:
        raise ValueError("Koşu sırasında config değişti.")


def _guard_run_inputs(
    config: Path, source: Path, expected_sha256: str, control: FeedbackControl
) -> None:
    _assert_config_unchanged(config, source, expected_sha256)
    control.assert_unchanged()


def _config_failure_evidence(config: Path | None, expected: bytes | None) -> dict[str, object]:
    """Retain byte/semantic fingerprints without dumping arbitrary config values."""
    if config is None or expected is None:
        return {"status": "not_initialized"}
    observed = config.read_bytes() if config.is_file() else None
    result: dict[str, object] = {
        "expected_sha256": hashlib.sha256(expected).hexdigest(),
        "actual_sha256": None if observed is None else hashlib.sha256(observed).hexdigest(),
        "expected_bytes": len(expected),
        "actual_bytes": None if observed is None else len(observed),
    }
    if observed is not None:
        import yaml

        try:
            before, after = yaml.safe_load(expected), yaml.safe_load(observed)
            result["yaml_semantically_equal"] = before == after
        except yaml.YAMLError:
            result["yaml_parse_status"] = "invalid"
    return result


async def run(args: argparse.Namespace) -> dict[str, object]:
    if sys.platform not in {"darwin", "linux"}:
        raise ValueError("K29: protected frozen actor adapter unavailable; not measured.")
    tasks = load_tasks(ROOT / "evals/suite/production.yaml")
    if args.repeat < 3:
        raise ValueError("En az üç tekrar gerekli.")
    args.out = args.out.resolve()
    if any(args.out.is_relative_to(root) for root in temporary_roots()):
        raise ValueError(
            "Protected host/output paths must be outside sandbox-writable temporary roots."
        )
    args.out.mkdir(parents=True, exist_ok=False)
    observations: list[dict[str, object]] = []
    payload: dict[str, Any] = {
        "schema": 1,
        "scope": "frozen-runtime",
        "observations": observations,
    }
    _checkpoint(args.out, payload, "in_progress")
    # The shell sandbox deliberately permits global temp writes. Keep runtime,
    # configuration, and observer outputs in protected siblings outside that set.
    with tempfile.TemporaryDirectory(
        prefix=".fusion-frozen-acceptance-", dir=args.out.parent
    ) as temporary:
        host = Path(temporary)
        config: Path | None = None
        original_config: bytes | None = None
        phase = "setup"
        try:
            archive_digest = sha256_file(args.archive)
            manifest_digest = sha256_file(args.manifest)
            executable, manifest = extract_runtime(args.archive, args.manifest, host / "runtime")
            provenance = json.loads(
                (executable.parent / "_internal/release-build.json").read_text()
            )
            expected = {
                "version": args.version,
                "commit": args.commit,
                "source_digest": _digest_entries(_source_entries(ROOT)),
                "scorer_digest": _digest_entries(_scorer_entries(ROOT)),
            }
            if any(provenance.get(name) != value for name, value in expected.items()):
                raise ValueError("Frozen build kaynak/sürüm/commit/puanlayıcı kimliği uyuşmuyor.")
            if manifest["runtime_version"] != args.version:
                raise ValueError("Frozen manifest sürümü uyuşmuyor.")
            home = host / "home"
            home.mkdir()
            config = host / "config.yaml"
            original_config = args.config.read_bytes()
            config.write_bytes(original_config)
            config_digest = hashlib.sha256(original_config).hexdigest()
            payload.update(
                target=manifest["target"],
                binding={
                    **expected,
                    "archive": args.archive.name,
                    "archive_sha256": archive_digest,
                    "manifest": args.manifest.name,
                    "manifest_sha256": manifest_digest,
                    "config_file_sha256": config_digest,
                },
            )
            _checkpoint(args.out, payload, "in_progress")
            env = {
                name: value
                for name, value in os.environ.items()
                if name in {"PATH", "SystemRoot", "WINDIR", "TMP", "TEMP", "TMPDIR"}
                or name in args.provider_env
            }
            env.update(
                HOME=str(home),
                USERPROFILE=str(home),
                FUSION_CONFIG=str(config),
                FUSION_SECRET_KEY=secrets.token_urlsafe(32),
                PYTHONUTF8="1",
            )
            for task in tasks:
                for index in range(1, args.repeat + 1):
                    root = args.out / "workspaces" / task.id / f"run-{index:02d}"
                    root.mkdir(parents=True)
                    for name, content in task.setup.items():
                        _write_seed_file(root, name, content)
                    control = prepare_feedback(
                        host / "bin" / f"{task.id}-{index}", root, task.id, config
                    )
                    feedback_manifest = control.manifest()
                    options = argparse.Namespace(
                        runtime_executable=str(executable),
                        runtime_env={**env, **control.environment},
                        runtime_config_guard=lambda control=control: _guard_run_inputs(
                            config, args.config, config_digest, control
                        ),
                        persist_mode=False,
                        kok=str(root.resolve()),
                        mod="auto",
                        gorev=[task.request],
                        soru_cevabi="ilk",
                        onay="once",
                        sure=task.budget.timeout_s if task.budget else 180,
                        chrome="",
                        log=False,
                    )
                    events = args.out / f"{task.id}-{index}.jsonl"
                    payload["active_execution"] = {
                        "task_id": task.id,
                        "repeat": index,
                        "events": events.name,
                    }
                    _checkpoint(args.out, payload, "in_progress")
                    phase = "driver"
                    started_at = time.time()
                    with events.open("wb") as stream:
                        observed = await drive(options, None, stream)
                    observations.append(
                        {
                            "task_id": task.id,
                            "repeat": index,
                            "started_at": started_at,
                            "finished_at": time.time(),
                            "candidate_digest": _digest_entries(_snapshot(root)),
                            "driver": observed,
                            "feedback": feedback_manifest,
                            "events": events.name,
                        }
                    )
                    payload.pop("active_execution", None)
                    _checkpoint(args.out, payload, "in_progress")
                    phase = "config_integrity_after_execution"
                    _guard_run_inputs(config, args.config, config_digest, control)
            phase = "final_integrity"
            verify_runtime_files(executable.parent, manifest)
            if (
                sha256_file(args.archive) != archive_digest
                or sha256_file(args.manifest) != manifest_digest
            ):
                raise ValueError("Koşu sırasında immutable runtime artefaktı/manifesti değişti.")
            if expected["source_digest"] != _digest_entries(_source_entries(ROOT)):
                raise ValueError("Frozen kabul sırasında checkout kaynak kimliği değişti.")
            _assert_config_unchanged(config, args.config, config_digest)
            payload["status"] = "completed"
            _checkpoint(args.out, payload, "completed")
            _atomic_json(args.out / "observations.json", payload)
            return payload
        except BaseException as error:
            # Preserve observations/fingerprints BEFORE TemporaryDirectory cleanup.
            # Partial diagnostics never carry publication authority.
            try:
                _atomic_json(
                    args.out / "failure-evidence.json",
                    {
                        "status": "invalid",
                        "acceptance_eligible": False,
                        "phase": phase,
                        "error_type": type(error).__name__,
                        "completed_executions": len(observations),
                        "config": _config_failure_evidence(config, original_config),
                    },
                )
                _checkpoint(args.out, payload, "invalid")
            except Exception as evidence_error:
                error.add_note(
                    f"Failure evidence could not be saved: {type(evidence_error).__name__}"
                )
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "manifest", "config", "out"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--provider-env", action="append", default=[])
    args = parser.parse_args(argv)
    asyncio.run(run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

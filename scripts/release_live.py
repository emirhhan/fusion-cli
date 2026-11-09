#!/usr/bin/env python3
"""Run the exact frozen artifact via the existing live driver; no oracle/PASS claim.

This stage may call the configured provider ONLY when explicitly executed. The
separate verifier stage re-inspects its output in a fresh CI environment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
import tempfile
import time
from pathlib import Path

from evals.executor import _snapshot, _write_seed_file
from evals.live_drive import drive
from evals.loader import load_tasks
from evals.profiles import _digest_entries, _scorer_entries, _source_entries
from scripts.release_manifest import ROOT, sha256_file
from scripts.release_runtime import extract_runtime, verify_runtime_files

from fusion_cli.core.shell_sandbox import temporary_roots


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
    # The shell sandbox deliberately permits global temp writes. Keep runtime,
    # configuration, and observer outputs in protected siblings outside that set.
    with tempfile.TemporaryDirectory(
        prefix=".fusion-frozen-acceptance-", dir=args.out.parent
    ) as temporary:
        host = Path(temporary)
        archive_digest = sha256_file(args.archive)
        manifest_digest = sha256_file(args.manifest)
        executable, manifest = extract_runtime(args.archive, args.manifest, host / "runtime")
        provenance = json.loads((executable.parent / "_internal/release-build.json").read_text())
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
        config.write_bytes(args.config.read_bytes())
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
        observations = []
        for task in tasks:
            for index in range(1, args.repeat + 1):
                root = args.out / "workspaces" / task.id / f"run-{index:02d}"
                root.mkdir(parents=True)
                for name, content in task.setup.items():
                    _write_seed_file(root, name, content)
                options = argparse.Namespace(
                    runtime_executable=str(executable),
                    runtime_env=env,
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
                        "events": events.name,
                    }
                )
        verify_runtime_files(executable.parent, manifest)
        if (
            sha256_file(args.archive) != archive_digest
            or sha256_file(args.manifest) != manifest_digest
        ):
            raise ValueError("Koşu sırasında immutable runtime artefaktı/manifesti değişti.")
        if expected["source_digest"] != _digest_entries(_source_entries(ROOT)):
            raise ValueError("Frozen kabul sırasında checkout kaynak kimliği değişti.")
        if sha256_file(config) != sha256_file(args.config):
            raise ValueError("Koşu sırasında config değişti.")
        payload = {
            "schema": 1,
            "scope": "frozen-runtime",
            "target": manifest["target"],
            "binding": {
                **expected,
                "archive": args.archive.name,
                "archive_sha256": archive_digest,
                "manifest": args.manifest.name,
                "manifest_sha256": manifest_digest,
                "config_file_sha256": sha256_file(config),
            },
            "observations": observations,
        }
        (args.out / "observations.json").write_text(json.dumps(payload, indent=2))
        return payload


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

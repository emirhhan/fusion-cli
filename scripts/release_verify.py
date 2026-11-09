#!/usr/bin/env python3
"""Fresh-job verifier: independent inspectors + frozen execution evidence -> signed acceptance.

Run on a clean CI job after actor jobs finish. The private signing key is created
here, never passed to the actor. Publication pins the public fingerprint through
this job's GitHub output, independently of report/artifact contents.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from evals.driver_config import validate_wire
from evals.effective_config import _digest
from evals.engine_proof import ImportedEngineProof
from evals.frozen_engine import PROTECTED_TARGETS
from evals.loader import load_tasks
from evals.profiles import _digest_entries, _scorer_entries, _source_entries
from scripts.release_attestation import sign
from scripts.release_manifest import (
    LIVE_ACCEPTANCE_MAX_AGE_S,
    ROOT,
    _validate_live_measurement,
    collect_artifacts,
    sha256_file,
)
from scripts.release_oracle import inspect_workspaces


def _calls(path: Path, expected_model: str) -> list[dict[str, str]]:
    started: Counter[str] = Counter()
    finished: Counter[str] = Counter()
    calls = []
    for line in path.read_text().splitlines():
        message = json.loads(line)
        event = message.get("veri", {})
        if event.get("olay") == "ModelCallStarted":
            started[event["call_id"]] += 1
        if event.get("olay") == "ModelCallFinished":
            identifier = event["call_id"]
            result = event["result"]
            if result.get("ok") is not True or not result.get("served_by"):
                raise ValueError("Model çağrısı başarısız veya gerçek model bilinmiyor.")
            if (
                event.get("requested_model") != expected_model
                or result["served_by"] != expected_model
            ):
                raise ValueError("Çağrılan/sunulan model onaylanmış modelle uyuşmuyor.")
            finished[identifier] += 1
            calls.append(
                {"call_id": identifier, "served_model": result["served_by"], "outcome": "ok"}
            )
    if not started or started != finished or any(value != 1 for value in started.values()):
        raise ValueError("Model çağrısı kapsamı eksik/tekrarlı.")
    return calls


async def verify_runs(args: argparse.Namespace) -> dict[str, Any]:
    tasks = load_tasks(ROOT / "evals/suite/production.yaml")
    source = _digest_entries(_source_entries(ROOT))
    scorer = _digest_entries(_scorer_entries(ROOT))
    artifacts = collect_artifacts(args.artifacts)
    hashes = {item["name"]: item["sha256"] for item in artifacts}
    directories = sorted(path.parent for path in args.runs.rglob("observations.json"))
    if not directories:
        raise ValueError("Frozen çalıştırma gözlemi yok.")
    targets: set[str] = set()
    calls: list[dict[str, str]] = []
    configs: list[list[str]] = []
    execution_ids: list[list[Any]] = []
    repeat = 0
    calls_by_task: Counter[str] = Counter()
    measured_at = time.time()
    for directory in directories:
        raw = json.loads((directory / "observations.json").read_text())
        if raw.get("status") != "completed" or raw.get("acceptance_eligible") is False:
            raise ValueError(
                "Frozen çalışma kaydı tamamlanmamış/geçersiz checkpoint; kabul edilemez."
            )
        binding = raw["binding"]
        target = raw["target"]
        if target not in PROTECTED_TARGETS:
            raise ValueError("K29: platform protected actor provenance unavailable; not measured.")
        if target in targets:
            raise ValueError("Frozen platform gözlemi yinelenmiş.")
        targets.add(target)
        for name, expected in (
            ("commit", args.commit),
            ("version", args.version),
            ("source_digest", source),
            ("scorer_digest", scorer),
            ("config_file_sha256", sha256_file(args.config)),
        ):
            if binding.get(name) != expected:
                raise ValueError(f"Frozen {name} kimliği uyuşmuyor.")
        if hashes.get(binding["manifest"]) != binding["manifest_sha256"]:
            raise ValueError("Çalıştırılan frozen manifest yayın adayıyla uyuşmuyor.")
        if hashes.get(binding["archive"]) != binding["archive_sha256"]:
            raise ValueError("Çalıştırılan frozen arşiv yayın adayıyla uyuşmuyor.")
        observations = raw["observations"]
        expected_grid = Counter((task.id, index) for task in tasks for index in range(1, 4))
        if Counter((item["task_id"], item["repeat"]) for item in observations) != expected_grid:
            raise ValueError("Frozen görev/tekrar kapsamı eksik veya yinelenmiş.")
        oracle = await inspect_workspaces(directory / "workspaces", repeat=3, isolated=True)
        oracle_by_id = {(row["task_id"], row["repeat"]): row for row in oracle}
        for item in observations:
            start, finish = item["started_at"], item["finished_at"]
            if (
                type(start) not in (int, float)
                or type(finish) not in (int, float)
                or not 0 <= time.time() - start <= LIVE_ACCEPTANCE_MAX_AGE_S
                or not start <= finish <= time.time()
            ):
                raise ValueError("Frozen gerçek çalıştırma zamanı eski/bilinmiyor veya gelecekte.")
            measured_at = min(measured_at, start)
            independent = oracle_by_id[item["task_id"], item["repeat"]]
            if independent["outcome"] != "passed":
                raise ValueError("Bağımsız oracle başarısız veya bilinmiyor.")
            if independent["candidate_digest"] != item["candidate_digest"]:
                raise ValueError("Denetlenen aday çalıştırma sonundaki baytlarla uyuşmuyor.")
            driver = item["driver"]
            if driver.get("hata") or driver.get("surucu_hatalari"):
                raise ValueError("Frozen sürücü gözlemi geçersiz.")
            proof = ImportedEngineProof(**driver["motor_kaniti"])
            if proof.source_digest != source or proof.requested_revision != args.commit:
                raise ValueError("Çalışan motor kaynak kimliği uyuşmuyor.")
            snapshots = [
                validate_wire(receipt, proof).effective for receipt in driver["efektif_kanitlar"]
            ]
            if not snapshots or any(snapshot.missing_fields for snapshot in snapshots):
                raise ValueError("Çalışan motor config gözlemi eksik.")
            expected_model_hash = _digest(args.model)
            if any(
                not any(
                    field.path == "selected_agent.model" and field.value == expected_model_hash
                    for field in snapshot.fields
                )
                for snapshot in snapshots
            ):
                raise ValueError("Efektif seçilmiş model onaylanmış modelle uyuşmuyor.")
            config_digest = _digest_entries(sorted({snapshot.digest for snapshot in snapshots}))
            configs.append([item["task_id"], config_digest])
            execution_ids.append([item["task_id"], repeat + item["repeat"]])
            event_path = directory / item["events"]
            if event_path.parent != directory or event_path.is_symlink():
                raise ValueError("Model olay yolu aday paketi dışına çıkamaz.")
            observed_calls = _calls(event_path, args.model)
            task = next(task for task in tasks if task.id == item["task_id"])
            if task.budget is None or len(observed_calls) > task.budget.max_model_calls:
                raise ValueError("Ölçülen model çağrısı görev bütçesini aştı.")
            calls_by_task[item["task_id"]] += len(observed_calls)
            calls.extend(observed_calls)
        repeat += 3
    if targets != set(args.target):
        raise ValueError("Frozen platform kümesi yayın politikasına uymuyor.")
    # Repetition does not alter the approved per-task observed configuration set.
    effective = _digest_entries(sorted({tuple(item) for item in configs}))
    if effective != args.effective_config_digest:
        raise ValueError("Efektif yapılandırma onaylanmış özetle uyuşmuyor.")
    payload: dict[str, Any] = {
        "scope": "frozen-runtime",
        "targets": sorted(targets),
        "binding": {
            "version": args.version,
            "commit": args.commit,
            "artifacts": hashes,
            "measured_at": measured_at,
        },
        "metadata": {
            "profile": "production",
            "model": args.model,
            "source_digest": source,
            "scorer_digest": scorer,
            "effective_config_digest": effective,
            "repeat": repeat,
            "task_ids": [task.id for task in tasks],
            "split_digest": sha256_file(ROOT / "evals/suite/production.yaml"),
            "execution_ids": execution_ids,
            "task_config_digests": configs,
            "calls": calls,
            "task_budgets": [
                [task.id, task.budget.max_model_calls, task.budget.timeout_s]
                for task in tasks
                if task.budget
            ],
        },
        "results": [
            {
                "task_id": task.id,
                "success": True,
                "false_success": False,
                "rate_limited": False,
                "runs": repeat,
                "passes": repeat,
                "model_calls": calls_by_task[task.id],
            }
            for task in tasks
        ],
        "limitations": ["installer_ui_not_measured", "trusted_ci_build_and_runner_hosts"],
    }
    _validate_live_measurement(payload["metadata"], payload["results"])
    if source != _digest_entries(_source_entries(ROOT)) or artifacts != collect_artifacts(
        args.artifacts
    ):
        raise ValueError("Doğrulama sırasında kaynak veya yayın artefaktları değişti.")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runs", "artifacts", "config", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("version", "commit"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--model")
    parser.add_argument("--effective-config-digest")
    parser.add_argument("--target", action="append", required=True)
    args = parser.parse_args(argv)
    from scripts.release_profile import profile_facts

    facts = profile_facts(args.config)
    if args.model is None:
        args.model = facts["model"]
    if args.effective_config_digest is None:
        args.effective_config_digest = facts["effective_config_digest"]
    payload = asyncio.run(verify_runs(args))
    args.out.mkdir(parents=True, exist_ok=False)
    report = args.out / "live-acceptance.json"
    report.write_text(json.dumps(payload, indent=2))
    # Generated only after actor stages have terminated; never persisted in the
    # published evidence directory or inherited by inspected candidate commands.
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    with tempfile.TemporaryDirectory(prefix="fusion-verifier-key-") as directory:
        private = Path(directory) / "private.key"
        private.write_bytes(
            Ed25519PrivateKey.generate().private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
        )
        private.chmod(0o600)
        fingerprint = sign(
            report, private, args.out / "live-acceptance.sig", args.out / "verifier.pub"
        )
    print(f"verifier_key_sha256={fingerprint}")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a") as stream:
            stream.write(f"verifier_key_sha256={fingerprint}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

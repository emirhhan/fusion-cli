"""Karşılaştırma receipt'i ürün sonucunu ve bilinmeyen eş koşulları değiştirmez."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from evals.kabul.comparison_report import read_comparison_metadata
from evals.kabul.engine_options import ComparisonValidity
from evals.kabul.model import Check, Inspection, Outcome, RunMetrics, RunRecord
from evals.kabul.report import render_text, write_report


def valid_proof() -> ComparisonValidity:
    return ComparisonValidity(
        import_verified=True,
        config_verified=True,
        source_digest="a" * 64,
        config_digests=("b" * 64,),
        engine_pid=123,
    )


def test_valid_sidecar_exports_typed_unknown_separate_from_product(tmp_path: Path) -> None:
    proof = valid_proof()
    (tmp_path / "comparison-proof.json").write_text(json.dumps(asdict(proof)))
    metadata = read_comparison_metadata(tmp_path, proof)
    record = RunRecord(
        "fixture",
        1,
        str(tmp_path),
        Outcome.PASSED,
        Inspection((Check("işlev", True),)),
        RunMetrics(),
        agent_ok=True,
        comparison=metadata,
    )
    path = tmp_path / "report.json"
    write_report(path, (record,), None)
    exported = json.loads(path.read_text())["kosular"][0]
    assert exported["agent_ok"] is True
    assert exported["outcome"] == "gecti"
    assert exported["comparison"]["engine_pid"] == 123
    assert exported["comparison"]["equal_conditions_verified"] is False
    assert "bilinmiyor" in render_text((record,))


@pytest.mark.parametrize(
    "field,value",
    [
        ("engine_pid", True),
        ("engine_pid", 124),
        ("source_digest", "bad"),
        ("source_digest", "c" * 64),
        ("config_digests", ["bad"]),
        ("authentication_status", "verified"),
        ("equal_conditions_verified", True),
        ("schema_version", True),
        ("config_verified", []),
        ("extra", "forged"),
    ],
)
def test_tampered_sidecar_cannot_become_comparison_success(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    expected = valid_proof()
    payload = asdict(expected)
    payload[field] = value
    (tmp_path / "comparison-proof.json").write_text(json.dumps(payload))
    metadata = read_comparison_metadata(tmp_path, expected)
    assert metadata.import_verified is False
    assert metadata.config_verified is False
    assert metadata.equal_conditions_verified is False
    assert metadata.source_digest is None


def test_absent_legacy_metadata_preserves_json_shape(tmp_path: Path) -> None:
    record = RunRecord(
        "fixture",
        1,
        str(tmp_path),
        Outcome.PASSED,
        Inspection((Check("işlev", True),)),
        RunMetrics(),
    )
    path = tmp_path / "report.json"
    write_report(path, (record,), None)
    assert "comparison" not in json.loads(path.read_text())["kosular"][0]
    assert "karşılaştırma" not in render_text((record,))


def test_sidecar_symlink_is_not_read_or_exported(tmp_path: Path) -> None:
    secret = tmp_path / ".env"
    secret.write_text("fake sentinel")
    (tmp_path / "comparison-proof.json").symlink_to(secret)
    metadata = read_comparison_metadata(tmp_path, valid_proof())
    assert metadata.import_verified is False
    assert "sentinel" not in str(asdict(metadata))


async def test_actual_runner_report_keeps_comparison_separate(tmp_path: Path, monkeypatch) -> None:
    from evals.kabul import runner
    from evals.kabul.model import Area

    from .test_kabul_engine_options import proof_fixture

    engine, driver = proof_fixture(tmp_path)
    driver["turlar"] = [{"ok": True, "metin": "yerel fixture", "sure_sn": 1}]
    workdir = tmp_path / "job"
    workdir.mkdir()
    (workdir / "engine-proof.json").write_bytes(engine.proof_path.read_bytes())

    async def fake_drive(*args, **kwargs):
        return driver

    monkeypatch.setattr(runner, "_drive", fake_drive)
    area = Area(
        "fixture", "public task", 5, lambda root, values: Inspection((Check("işlev", True),))
    )
    record = await runner.run_job(
        runner.Job(area, 1, workdir),
        runner.RunnerOptions(1, 0, None, engine.selection.source_root, engine.manifest),
        runner.asyncio.Lock(),
    )
    assert record.agent_ok is True
    assert record.outcome is Outcome.PASSED
    assert record.comparison is not None
    assert record.comparison.import_verified is True
    assert record.comparison.config_verified is True
    assert record.comparison.engine_pid == 123
    assert record.comparison.equal_conditions_verified is False

"""Kabul motor seçenekleri üretim ve karşılaştırma kanıtını ayırır."""

from pathlib import Path

import pytest
from evals.kabul.model import Area, Inspection
from evals.kabul.runner import Job, RunnerOptions, _driver_command


def job(tmp_path, attempt=1):
    return Job(
        Area("fixture", "task", 5, lambda root, values: Inspection()),
        attempt,
        tmp_path / f"run-{attempt}",
    )


def test_absent_engine_options_preserve_driver_command(tmp_path):
    current = job(tmp_path)
    options = RunnerOptions(1, 0, None)
    command = _driver_command(current, current.workdir, "task", options)
    assert command == _driver_command(current, current.workdir, "task")
    assert "--engine-source" not in command
    assert "--engine-manifest" not in command
    assert "--engine-proof" not in command


def test_partial_engine_selection_rejected_before_spawn(tmp_path):
    with pytest.raises(ValueError):
        RunnerOptions(1, 0, None, engine_source=tmp_path / "reference")


def test_selected_current_reference_flags_and_distinct_job_proofs(tmp_path):
    for name in ("current", "reference"):
        options = RunnerOptions(1, 0, None, tmp_path / name, tmp_path / f"{name}.json")
        commands = [_driver_command(job(tmp_path, i), tmp_path, "task", options) for i in (1, 2)]
        for command in commands:
            assert command[command.index("--engine-source") + 1] == str(tmp_path / name)
            assert command[command.index("--engine-manifest") + 1] == str(tmp_path / f"{name}.json")
        proofs = [Path(command[command.index("--engine-proof") + 1]) for command in commands]
        assert proofs[0] != proofs[1]
        assert proofs[0].parent == job(tmp_path).workdir


def proof_fixture(tmp_path):
    import json
    from dataclasses import asdict

    from evals.driver_config import ConfigReceipt
    from evals.driver_engine import from_options
    from evals.effective_config import project_effective
    from evals.engine_proof import ImportedEngineProof

    from .fakes import make_config
    from .test_live_drive_engine_proof import settings

    args, _ = settings(tmp_path)
    selected = from_options(args)
    root = selected.selection.source_root
    proof = ImportedEngineProof(
        123,
        str(root / "src/fusion_cli/__init__.py"),
        str(root / "src/fusion_cli/cli/app.py"),
        str(root),
        selected.source_digest,
        selected.selection.requested_revision,
    )
    selected.proof_path.write_text(json.dumps(asdict(proof)))
    config = make_config()
    receipt = ConfigReceipt(
        1,
        proof.pid,
        proof.source_digest,
        proof.requested_revision,
        "unverified",
        project_effective(config, config.agent, "general"),
    )
    driver = json.loads(
        json.dumps(
            {
                "motor_kaniti": asdict(proof),
                "kontrollu_ayar_kaniti": True,
                "efektifi": "not read",
                "efektif_kanitlar": [asdict(receipt)],
            }
        )
    )
    return selected, driver


@pytest.mark.parametrize("mode", ["valid", "missing", "pid", "source", "config", "snapshot"])
def test_comparison_gate_is_separate_and_does_not_claim_equality(tmp_path, mode):
    from evals.kabul.engine_options import comparison_validity

    engine, driver = proof_fixture(tmp_path)
    if mode == "missing":
        engine.proof_path.unlink()
    elif mode == "pid":
        driver["motor_kaniti"]["pid"] += 1
    elif mode == "source":
        driver["motor_kaniti"]["source_digest"] = "c" * 64
    elif mode == "config":
        driver["kontrollu_ayar_kaniti"] = False
    elif mode == "snapshot":
        driver["efektif_kanitlar"][0]["effective"]["digest"] = "c" * 64
    proof = comparison_validity(driver, engine)
    assert proof.config_verified is (mode == "valid")
    assert proof.equal_conditions_verified is False
    assert proof.selected_model_preflight_verified is False
    assert proof.authentication_status == proof.cache_initial_state == "unknown"


async def test_invalid_manifest_never_spawns_driver(tmp_path, monkeypatch):
    from evals.kabul import runner

    async def forbidden(*args, **kwargs):
        raise AssertionError("Alt süreç başlamamalı.")

    monkeypatch.setattr(runner.asyncio, "create_subprocess_exec", forbidden)
    options = RunnerOptions(1, 0, None, tmp_path / "missing", tmp_path / "missing.json")
    with pytest.raises(OSError):
        await runner.run_job(job(tmp_path), options, runner.asyncio.Lock())


async def test_missing_config_proof_does_not_rewrite_product_result(tmp_path, monkeypatch):
    import json

    from evals.kabul import runner

    engine, driver = proof_fixture(tmp_path)
    driver["kontrollu_ayar_kaniti"] = False
    driver["turlar"] = [{"ok": True, "metin": "fixture", "sure_sn": 1}]
    current = job(tmp_path)
    current.workdir.mkdir()
    (current.workdir / "engine-proof.json").write_bytes(engine.proof_path.read_bytes())

    async def fake_drive(*args, **kwargs):
        return driver

    monkeypatch.setattr(runner, "_drive", fake_drive)
    options = RunnerOptions(1, 0, None, engine.selection.source_root, engine.manifest)
    record = await runner.run_job(current, options, runner.asyncio.Lock())
    assert record.agent_ok is True
    stored = json.loads((current.workdir / "comparison-proof.json").read_text())
    assert stored["import_verified"] is True
    assert stored["config_verified"] is False


def test_cli_invalid_selection_rejected_before_model_preflight(tmp_path, monkeypatch):
    import sys

    from evals.kabul import cli

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "kabul",
            "--alan",
            "html_oyun",
            "--cikti",
            str(tmp_path / "out"),
            "--engine-source",
            str(tmp_path / "missing"),
            "--engine-manifest",
            str(tmp_path / "missing.json"),
        ],
    )
    monkeypatch.setattr(
        cli, "run_preflight", lambda *args: pytest.fail("Model önkontrolü başlamamalı.")
    )
    with pytest.raises(OSError):
        cli.main()


def test_relative_selection_uses_caller_absolute_paths_before_child_cwd(tmp_path, monkeypatch):
    engine, _ = proof_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    options = RunnerOptions(1, 0, None, Path("engine"), Path("manifest.json"))
    relative_job = Job(job(tmp_path).area, 1, Path("empty-work/run"))
    command = _driver_command(relative_job, tmp_path, "task", options)
    assert command[command.index("--engine-source") + 1] == str(engine.selection.source_root)
    assert command[command.index("--engine-manifest") + 1] == str(engine.manifest)
    assert command[command.index("--engine-proof") + 1] == str(
        tmp_path / "empty-work/run/engine-proof.json"
    )

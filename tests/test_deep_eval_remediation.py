"""Derin denetim D01–D03: ölçümün sahte başarıyı gizlememesi."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from evals.loader import load_tasks

ROOT = Path(__file__).resolve().parents[1]


def _production_task(fragment):
    return next(
        task for task in load_tasks(ROOT / "evals/suite/production.yaml") if fragment in task.id
    )


def _criterion(task, root):
    for name, content in task.setup.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return lambda: subprocess.run(
        task.criterion.command.replace("python ", f"{sys.executable} "),
        shell=True,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": f"{ROOT}:{ROOT / 'src'}"},
    )


def test_mcp_stdout_ping_pong_gercek_protokol_cagrisi_sayilmaz(tmp_path):
    run = _criterion(_production_task("mcp"), tmp_path)
    (tmp_path / "mcp_candidate.py").write_text("print('ping pong')\n")
    assert run().returncode != 0


def test_buyuk_artifact_gercekten_buyuktur_ve_orta_bolum_silinemez(tmp_path):
    task = _production_task("buyuk-artifact")
    original = task.setup["large.py"]
    assert len(original.encode()) >= 131072
    run = _criterion(task, tmp_path)
    (tmp_path / "large.py").write_text('HEADER = "keep"\nTARGET = 42\nFOOTER = "keep-too"\n')
    assert run().returncode != 0
    (tmp_path / "large.py").write_text(original.replace("TARGET = 1\n", "TARGET = 42\n"))
    result = run()
    assert result.returncode == 0, result.stderr


async def test_headless_onay_tekrari_raporlanir_insan_suresi_uydurulmaz():
    from evals.agent_runner import _EvalApproval

    from fusion_cli.core.tools import Tool
    from fusion_cli.engines.agent.approval import build_request

    tool = Tool(name="run_shell", description="", parameters={}, run=lambda a, c: None)
    approval = _EvalApproval()
    await approval.decide(build_request(tool, {"command": "echo x > ../outside.txt"}))
    await approval.decide(build_request(tool, {"command": "echo x > ../outside.txt"}))
    await approval.decide(build_request(tool, {"command": "echo y > ../outside.txt"}))
    metrics = approval.interactions
    assert metrics.approval_requests == 3
    assert metrics.repeated_requests == 1
    assert metrics.human_response_seconds is None
    assert metrics.pending_recovery_verified is None
    assert metrics.restart_persistence_verified is None


def test_release_manifest_canli_olcum_yokken_olculmedi_der(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "deep_release_manifest", ROOT / "scripts/release_manifest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "app.dmg").write_bytes(b"package")
    out = tmp_path / "out"
    assert (
        module.main(
            [
                "--version",
                "1.0",
                "--commit",
                "a" * 40,
                "--kits-commit",
                "b" * 40,
                "--artifacts",
                str(artifacts),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    manifest = json.loads((out / "release-manifest.json").read_text())
    assert manifest["liveAcceptance"]["status"] == "not_measured"
    assert manifest["claimsReady"] is False


@pytest.mark.parametrize(
    "change",
    (
        "stale",
        "package",
        "calls",
        "provider",
        "missing_task",
        "duplicate_execution",
        "missing_config",
        "invalid_digest",
        "unknown_failure",
        "bool_runs",
        "duplicate_call",
        "missing_task_ids",
        "wrong_repeat_count",
        "duplicate_budget",
        "bool_model_calls",
    ),
)
def test_canli_rapor_eski_paket_veya_model_cagrisi_yoksa_kabul_edilmez(tmp_path, change):
    spec = importlib.util.spec_from_file_location(
        "deep_release_manifest", ROOT / "scripts/release_manifest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    artifacts = [{"name": "app.dmg", "sha256": "c" * 64, "size": 7}]
    report = {
        "binding": {"commit": "a" * 40, "artifacts": {"app.dmg": "c" * 64}, "measured_at": 1000},
        "metadata": {
            "profile": "production",
            "model": "test/model",
            "effective_config_digest": "d" * 64,
            "source_digest": "e" * 64,
            "repeat": 3,
            "task_budgets": [["one", 30, 180]],
            "calls": [{"served_model": "test/model", "outcome": "ok"}],
        },
        "results": [
            {
                "task_id": "one",
                "success": True,
                "runs": 3,
                "passes": 3,
                "model_calls": 1,
                "false_success": False,
                "rate_limited": False,
            }
        ],
    }
    identifiers = [
        "godot-asset-lisansli",
        "mcp-stdio-listele-cagir",
        "yanlis-hedefte-yeniden-planla",
        "buyuk-artifact-korumali-duzenleme",
        "json-dosya-izolasyonu",
    ]
    report["metadata"]["task_ids"] = identifiers
    report["metadata"]["split_digest"] = hashlib.sha256(
        (ROOT / "evals/suite/production.yaml").read_bytes()
    ).hexdigest()
    report["metadata"]["task_budgets"] = [[name, 30, 180] for name in identifiers]
    report["metadata"]["calls"] *= 15
    report["results"] = [{**report["results"][0], "task_id": name} for name in identifiers]
    report["metadata"]["execution_ids"] = [
        [name, index] for name in identifiers for index in range(1, 4)
    ]
    report["metadata"]["task_config_digests"] = [
        [name, "d" * 64] for name, _ in report["metadata"]["execution_ids"]
    ]
    report["metadata"]["calls"] = [
        {"call_id": f"call-{index}", "served_model": "test/model", "outcome": "ok"}
        for index in range(15)
    ]
    path = tmp_path / "live.json"
    path.write_text(json.dumps(report))
    assert module.live_acceptance(path, artifacts, "a" * 40, now=1001)["status"] == "passed"
    candidate = json.loads(json.dumps(report))
    if change == "stale":
        candidate["binding"]["measured_at"] = 0
    if change == "package":
        candidate["binding"]["artifacts"]["app.dmg"] = "0" * 64
    if change == "calls":
        candidate["metadata"]["calls"] = []
    if change == "provider":
        candidate["results"][0]["rate_limited"] = True
    if change == "missing_task":
        candidate["results"].pop()
    if change == "duplicate_execution":
        candidate["metadata"]["execution_ids"][-1] = candidate["metadata"]["execution_ids"][0]
    if change == "missing_config":
        candidate["metadata"]["task_config_digests"].pop()
    if change == "invalid_digest":
        candidate["metadata"]["source_digest"] = "unknown"
    if change == "unknown_failure":
        candidate["results"][0]["false_success"] = None
    if change == "bool_runs":
        candidate["results"][0]["runs"] = True
    if change == "duplicate_call":
        candidate["metadata"]["calls"][-1] = candidate["metadata"]["calls"][0]
    if change == "missing_task_ids":
        candidate["metadata"]["task_ids"] += [identifiers[0]]
    if change == "wrong_repeat_count":
        candidate["results"][0]["runs"] = candidate["results"][0]["passes"] = 4
    if change == "duplicate_budget":
        candidate["metadata"]["task_budgets"] += [candidate["metadata"]["task_budgets"][0]]
    if change == "bool_model_calls":
        candidate["results"][0]["model_calls"] = True
    path.write_text(json.dumps(candidate))
    with pytest.raises(SystemExit):
        module.live_acceptance(path, artifacts, "a" * 40, now=200000 if change == "stale" else 1001)


def test_rapor_onay_metrigi_ve_saglayici_olculemedi_bilgisini_korur():
    from evals.execution import TaskExecution
    from evals.interactions import InteractionMetrics
    from evals.metrics import RunReport, merge_runs, score_task
    from evals.report import report_from_dict, report_to_dict
    from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

    task = EvalTask("one", "test", SuccessCriterion(CriterionKind.KEYWORD, keyword="ok"))
    result = score_task(
        task,
        TaskExecution(
            "one", output_text="ok", rate_limited=True, interactions=InteractionMetrics(3, 1)
        ),
    )
    merged = merge_runs([result, result])
    payload = report_to_dict(RunReport((merged,)))
    restored = report_from_dict(payload).results[0]
    assert restored.rate_limited is True
    assert restored.interactions.approval_requests == 6
    assert restored.interactions.repeated_requests == 2
    assert restored.interactions.human_response_seconds is None


def test_setup_tarifi_ayni_executor_icin_sinirli_metin_uretir():
    from evals.loader import parse_task

    from fusion_cli.core.errors import EvalError

    task = {
        "id": "recipe",
        "request": "edit",
        "criterion": {"kind": "keyword", "keyword": "ok"},
        "setup": {"large.txt": {"segments": ["head\n", {"repeat": "row\n", "count": 3}, "tail\n"]}},
    }
    assert parse_task(task).setup["large.txt"] == "head\nrow\nrow\nrow\ntail\n"
    for count in (-1, True, 999999999):
        task["setup"]["large.txt"]["segments"][1]["count"] = count
        with pytest.raises(EvalError):
            parse_task(task)


def test_kaynak_ozeti_production_kabul_kodunu_da_kapsar(tmp_path):
    from evals.profiles import _source_entries

    fixture = tmp_path / "evals/fixtures/production_acceptance.py"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("value = 1\n")
    first = _source_entries(tmp_path)
    fixture.write_text("value = 2\n")
    assert _source_entries(tmp_path) != first

"""Production değerlendirme profilinin yayın sözleşmesi."""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
from pathlib import Path

from evals.executor import AgentRunObservation, AgentTaskExecutor
from evals.loader import load_tasks
from evals.metrics import RunReport, TaskResult
from evals.profiles import EvalProfile
from evals.report import report_to_dict
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.mcp_bridge.service import McpConnectionService

from .test_eval_executor import _FakeClock, _task

ROOT = Path(__file__).resolve().parents[1]


def test_production_suite_bes_gercek_senaryo_ailesini_icerir():
    root = Path(__file__).resolve().parents[1]
    tasks = load_tasks(root / "evals" / "suite" / "production.yaml")
    ids = {task.id for task in tasks}

    assert len(tasks) == 5
    assert any("godot-asset" in item for item in ids)
    assert any("oauth-mcp" in item for item in ids)
    assert any("yeniden-planla" in item for item in ids)
    assert any("buyuk-artifact" in item for item in ids)
    assert any("sohbet-izolasyonu" in item for item in ids)
    assert EvalProfile.PRODUCTION.value == "production"


def test_mcp_kabul_olcutu_cagrilabilir_betik_istemiyor(tmp_path):
    tasks = load_tasks(ROOT / "evals" / "suite" / "production.yaml")
    task = next(item for item in tasks if item.id == "oauth-mcp-yasam-dongusu")
    (tmp_path / "oauth_mcp_server.py").write_text(
        'TOOLS = {"ping": lambda: "pong"}\n', encoding="utf-8"
    )
    (tmp_path / "smoke_test.py").write_text(
        "from oauth_mcp_server import TOOLS\n"
        "print('Araçlar:', ', '.join(TOOLS))\n"
        "print('ping:', TOOLS['ping']())\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        task.criterion.command,
        cwd=tmp_path,
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_rapor_tekil_kosu_ile_kati_guvenilirligi_ayri_yazar():
    report = RunReport(
        (
            TaskResult("kararli", True, True, 0, 1, 1.0, runs=3, passes=3),
            TaskResult("kararsiz", False, False, 1, 2, 2.0, runs=3, passes=2),
        )
    )

    summary = report_to_dict(report)["summary"]

    assert isinstance(summary, dict)
    assert summary["run_success_rate"] == 5 / 6
    assert summary["strict_task_success_rate"] == 0.5


async def test_yerel_http_mcp_fixture_initialize_listele_cagir_ve_cikis_yapar():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(ROOT / "evals" / "fixtures" / "oauth_mcp_server.py"),
        "--port",
        str(port),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    config = McpServerConfig(
        "fixture",
        transport=McpTransport.STREAMABLE_HTTP,
        url=f"http://127.0.0.1:{port}/mcp",
    )
    try:
        for _ in range(50):
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.close()
                await writer.wait_closed()
                del reader
                break
            except OSError:
                await asyncio.sleep(0.1)
        async with McpClient((config,), timeout_seconds=5) as client:
            tools = await client.list_tools("fixture")
            result = await client.call("fixture", "ping", {})
        assert {tool.name for tool in tools} == {"ping"}
        assert result.ok is True and "pong" in result.output

        service = McpConnectionService()
        await service.logout(config)
        assert service.login_status("fixture").state == "kapali"
    finally:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=5)


async def test_eval_rejects_candidate_symlink_before_reading_target(tmp_path, monkeypatch):
    import pytest

    from fusion_cli.core.errors import EvalError

    outside = tmp_path / "outside.txt"
    outside.write_text("özel içerik")
    original = Path.read_bytes

    def guarded_read(path):
        if path == outside or path.is_symlink():
            pytest.fail("Sembolik bağlantının hedefi okunmamalı")
        return original(path)

    class Runner:
        async def run(self, request, *, root, **kwargs):
            (root / "leak.txt").symlink_to(outside)
            return AgentRunObservation("", 0)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    with pytest.raises(EvalError, match="bağlantı"):
        await AgentTaskExecutor(
            Runner(),
            workspace_root=tmp_path / "runs",
            clock=_FakeClock(0.0, 1.0),
        ).run(_task("local", SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="x")))


async def test_clean_acceptance_cannot_be_shadowed_by_candidate_python_module(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("PYTHONOPTIMIZE", "1")
    task = EvalTask(
        id="shadow",
        request="dosyayı düzelt",
        setup={"notlar.txt": ""},
        criterion=SuccessCriterion(
            kind=CriterionKind.EXIT_CODE,
            expected_exit_code=0,
            command="python -m evals.fixtures.fusion_research.acceptance T01",
        ),
    )

    class ShadowRunner:
        async def run(self, request, *, root, **kwargs):
            package = root / "evals/fixtures/fusion_research"
            package.mkdir(parents=True)
            for directory in [root / "evals", root / "evals/fixtures", package]:
                (directory / "__init__.py").write_text("")
            (package / "acceptance.py").write_text("pass\n")
            return AgentRunObservation("tamam", 0)

    execution = await AgentTaskExecutor(
        ShadowRunner(),
        workspace_root=tmp_path,
        clock=_FakeClock(0.0, 1.0),
    ).run(task)
    assert execution.exit_code != 0


async def test_generic_python_acceptance_bootstrap_ignores_candidate_modules(tmp_path):
    from .test_eval_executor import _FakeRunner

    task = EvalTask(
        id="bootstrap",
        request="hesabı düzelt",
        setup={
            "product.py": "def calculate():\n    return 0\n",
            "test_behavior.py": (
                "from product import calculate\n\ndef test_result():\n    assert calculate() == 7\n"
            ),
        },
        criterion=SuccessCriterion(
            kind=CriterionKind.EXIT_CODE, expected_exit_code=0, command="python -m pytest -q"
        ),
    )
    for module in ("pytest.py", "sitecustomize.py", "usercustomize.py"):
        bad = await AgentTaskExecutor(
            _FakeRunner(files={module: "raise SystemExit(0)\n"}),
            workspace_root=tmp_path,
            clock=_FakeClock(0.0, 1.0),
        ).run(task)
        assert bad.exit_code != 0, module
        good = await AgentTaskExecutor(
            _FakeRunner(
                files={
                    module: "raise SystemExit(0)\n",
                    "product.py": "def calculate():\n    return 7\n",
                }
            ),
            workspace_root=tmp_path,
            clock=_FakeClock(0.0, 1.0),
        ).run(task)
        assert good.exit_code == 0, module


async def test_acceptance_explicit_pytest_config_is_frozen(tmp_path):
    from .test_eval_executor import _FakeRunner

    task = EvalTask(
        id="config",
        request="hesabı düzelt",
        setup={
            "product.py": "def calculate():\n    return 0\n",
            "checks.ini": "[pytest]\n",
            "test_behavior.py": (
                "from product import calculate\n\ndef test_result():\n    assert calculate() == 7\n"
            ),
            "test_smoke.py": "def test_smoke():\n    assert True\n",
        },
        criterion=SuccessCriterion(
            kind=CriterionKind.EXIT_CODE,
            expected_exit_code=0,
            command="python -m pytest -q -c checks.ini",
        ),
    )
    attack = {"checks.ini": "[pytest]\naddopts = --ignore=test_behavior.py\n"}
    bad = await AgentTaskExecutor(
        _FakeRunner(files=attack),
        workspace_root=tmp_path,
        clock=_FakeClock(0.0, 1.0),
    ).run(task)
    assert bad.exit_code != 0
    good = await AgentTaskExecutor(
        _FakeRunner(files={**attack, "product.py": "def calculate():\n    return 7\n"}),
        workspace_root=tmp_path,
        clock=_FakeClock(0.0, 1.0),
    ).run(task)
    assert good.exit_code == 0


async def test_trusted_workspace_ancestor_symlink_allows_normal_product_edit(tmp_path):
    from .test_eval_executor import _FakeRunner

    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    runner = _FakeRunner(files={"product.py": "value = 7\n"})
    task = EvalTask(
        id="normal",
        request="değeri yaz",
        criterion=SuccessCriterion(
            kind=CriterionKind.EXIT_CODE,
            expected_exit_code=0,
            command='python -c "import product; assert product.value == 7"',
        ),
    )
    result = await AgentTaskExecutor(
        runner,
        workspace_root=alias / "runs",
        clock=_FakeClock(0.0, 1.0),
    ).run(task)
    assert result.exit_code == 0
    assert runner.roots[0].is_relative_to(real)


async def test_explicit_pytest_collection_input_is_frozen(tmp_path):
    from .test_eval_executor import _FakeRunner

    task = EvalTask(
        id="explicit-check",
        request="hesabı düzelt",
        setup={
            "product.py": "value = 0\n",
            "checks.py": "import product\n\ndef test_value():\n    assert product.value == 7\n",
        },
        criterion=SuccessCriterion(
            kind=CriterionKind.EXIT_CODE,
            expected_exit_code=0,
            command="python -m pytest -q checks.py",
        ),
    )
    execution = await AgentTaskExecutor(
        _FakeRunner(files={"checks.py": "def test_value():\n    assert True\n"}),
        workspace_root=tmp_path,
        clock=_FakeClock(0.0, 1.0),
    ).run(task)
    assert execution.exit_code != 0


async def test_unsupported_python_acceptance_form_is_explicitly_unavailable(tmp_path):
    from evals.executor import EXIT_VERIFICATION_UNAVAILABLE

    from .test_eval_executor import _FakeRunner

    task = EvalTask(
        id="unsupported",
        request="yanıtla",
        criterion=SuccessCriterion(
            kind=CriterionKind.EXIT_CODE,
            expected_exit_code=0,
            command="PYTHONPATH=. python -m pytest -q",
        ),
    )
    execution = await AgentTaskExecutor(
        _FakeRunner(files={"pytest.py": "pass\n"}),
        workspace_root=tmp_path,
        clock=_FakeClock(0.0, 1.0),
    ).run(task)
    assert execution.exit_code == EXIT_VERIFICATION_UNAVAILABLE


async def test_cd_chain_freezes_actual_subdirectory_acceptance_inputs(tmp_path):
    from .test_eval_executor import _FakeRunner

    check = "import product\n\ndef test_value():\n    assert product.value == 7\n"
    setup = {
        "sub/product.py": "value = 0\n",
        "sub/checks.ini": "[pytest]\n",
        "sub/checks.py": check,
        "sub/test_behavior.py": check,
        "sub/test_smoke.py": "def test_smoke():\n    assert True\n",
    }
    cases = (
        (
            "cd sub && python -m pytest -q -c checks.ini",
            {"sub/checks.ini": "[pytest]\naddopts = --ignore=test_behavior.py\n"},
        ),
        (
            "cd sub && python -m pytest -q -c checks.ini checks.py test_smoke.py",
            {"sub/checks.py": "def test_value():\n    assert True\n"},
        ),
    )
    for command, tamper in cases:
        task = EvalTask(
            "subdir",
            "değeri düzelt",
            SuccessCriterion(
                kind=CriterionKind.EXIT_CODE,
                expected_exit_code=0,
                command=command,
            ),
            setup=setup,
        )
        for attack in ({}, tamper):
            for value in (0, 7):
                execution = await AgentTaskExecutor(
                    _FakeRunner(files={**attack, "sub/product.py": f"value = {value}\n"}),
                    workspace_root=tmp_path,
                    clock=_FakeClock(0.0, 1.0),
                ).run(task)
                assert (execution.exit_code == 0) is (value == 7), (attack, execution)

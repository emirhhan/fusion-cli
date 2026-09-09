"""Production değerlendirme profilinin yayın sözleşmesi."""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

from evals.loader import load_tasks
from evals.metrics import RunReport, TaskResult
from evals.profiles import EvalProfile
from evals.report import report_to_dict

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.mcp_bridge.client import McpClient
from fusion_cli.mcp_bridge.service import McpConnectionService

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

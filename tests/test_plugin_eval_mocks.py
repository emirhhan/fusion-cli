"""`plugin eval --mocks`: MCP sahte sunucuları, yerine koyma ve koşu durdurma (#380)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from fusion_cli.config.models import McpServerConfig
from fusion_cli.config.plugin_eval_env import MCP_ENV, MOCK_MODULE, with_eval_mocks
from fusion_cli.core.plugins import PluginError
from fusion_cli.tools import plugin_eval_run as run
from fusion_cli.tools.plugin_eval import RunTrace, load_cases
from fusion_cli.tools.plugin_eval_mock_server import call_tool, serve
from fusion_cli.tools.plugin_eval_mocks import (
    LOG_ENV,
    STUB,
    load_mocks,
    load_server,
    mock_env,
    mock_notes,
)


def _mocks(tmp_path: Path) -> Path:
    folder = tmp_path / "evals" / "mocks" / "tracker"
    folder.mkdir(parents=True)
    (folder / "create_issue.md").write_text(
        '---\nexpect:\n  project: WEB\n---\n{"id": 7, "title": "{{input.title}}"}\n',
        "utf-8",
    )
    (folder / "fail.md").write_text("---\nerror: true\n---\nservis kapalı\n", "utf-8")
    (folder / "_tools.json").write_text(
        json.dumps({"tools": [{"name": "create_issue", "description": "Kayıt aç",
                               "inputSchema": {"type": "object"}}]}),
        "utf-8",
    )  # fmt: skip
    return folder


def test_hazir_sonuc_girdiyi_yansitir_ve_expect_ihlali_durdurur(tmp_path, monkeypatch):
    server = load_server(_mocks(tmp_path))
    log = tmp_path / "calls.jsonl"
    monkeypatch.setenv(LOG_ENV, str(log))

    ok = call_tool(server, "create_issue", {"project": "WEB", "title": "Düğme"})
    assert ok == {"content": [{"type": "text", "text": '{"id": 7, "title": "Düğme"}'}],
                  "isError": False}  # fmt: skip
    wrong = call_tool(server, "create_issue", {"project": "API", "title": "x"})
    assert wrong["isError"] is True and "expected project" in wrong["content"][0]["text"]
    assert call_tool(server, "fail", {})["isError"] is True
    rows = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
    assert [bool(r["abort"]) for r in rows] == [False, True, False]


def test_json_rpc_tools_list_ve_call(tmp_path):
    server = load_server(_mocks(tmp_path))
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "create_issue", "arguments": {"project": "WEB", "title": "t"}}},
    ]  # fmt: skip
    out = io.StringIO()
    serve(server, io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n"), out)

    replies = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3]
    tools = {t["name"]: t for t in replies[1]["result"]["tools"]}
    assert tools["create_issue"]["description"] == "Kayıt aç"
    assert replies[2]["result"]["isError"] is False


def test_taslak_ve_gecersiz_klasor_adlari_reddedilir(tmp_path):
    folder = _mocks(tmp_path)
    (folder / "stub.md").write_text(f"{STUB}\n", "utf-8")
    with pytest.raises(PluginError, match="still a stub"):
        load_server(folder)
    bad = tmp_path / "evals" / "mocks" / "a__b"
    bad.mkdir()
    with pytest.raises(PluginError, match="separator"):
        load_server(bad)


def test_sahtesiz_sunucu_baslamaz_bilinmeyen_sahte_hata(tmp_path):
    _mocks(tmp_path)
    mocks = load_mocks(tmp_path / "evals")
    assert mock_notes(("tracker", "drive"), mocks, mode="record", allow_real=False) == (
        'MCP server "drive" has no mock and its tools are unavailable this run; add '
        "mocks/drive/ to mock it, or pass --allow-real-servers to run the plugin's real server "
        "(as you, outside the sandbox)",
    )
    assert mock_notes(("tracker",), mocks, mode="off", allow_real=False) == ()
    with pytest.raises(PluginError, match="no server the plugins declare"):
        mock_notes(("drive",), mocks, mode="record", allow_real=False)


def test_alt_surec_yapilandirmasi_sahteyi_kullanir(tmp_path, monkeypatch):
    mocks = load_mocks(_mocks(tmp_path).parent.parent)
    servers = (
        McpServerConfig("plugin:rapor:tracker", command="node", args=("srv.js",)),
        McpServerConfig("plugin:rapor:drive", command="node"),
    )
    monkeypatch.setenv(MCP_ENV, mock_env("record", mocks, allow_real=False)[MCP_ENV])
    (mocked,) = with_eval_mocks(servers)
    assert mocked.name == "plugin:rapor:tracker" and mocked.args[:2] == ("-m", MOCK_MODULE)
    monkeypatch.setenv(MCP_ENV, mock_env("record", mocks, allow_real=True)[MCP_ENV])
    assert [s.name for s in with_eval_mocks(servers)][1] == "plugin:rapor:drive"
    monkeypatch.setenv(MCP_ENV, mock_env("off", {}, allow_real=False)[MCP_ENV])
    assert with_eval_mocks(servers) == servers
    monkeypatch.delenv(MCP_ENV)
    assert with_eval_mocks(servers) == servers
    with pytest.raises(PluginError):
        mock_env("kayit", mocks, allow_real=False)


def test_expect_ihlali_kosu_puanini_sifirlar(tmp_path):
    case_dir = tmp_path / "evals" / "a"
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text("---\nruns: 1\n---\nKayıt aç.\n", "utf-8")
    (case_dir / "graders" / "g.md").write_text("---\ntype: regex\n---\nTAMAM\n", "utf-8")
    cases = load_cases(tmp_path / "evals")

    def runner(spec):
        assert spec.log is not None
        spec.log.write_text(json.dumps({"abort": ["create_issue: expected project"]}) + "\n")
        return RunTrace("TAMAM", (), spec.workdir)

    result = run.run_suite(cases, None, runner=runner, judge=lambda _p: 1.0)
    (only,) = result["cases"][0]["with"]["runs"]
    assert only["score"] == 0.0 and only["aborted"] == ["create_issue: expected project"]

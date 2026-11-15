"""PostToolUse `tool_response` / `duration_ms` Claude Code şeklinde (#100).

Claude: Write yanıtı `{filePath, type: "create"|"update", ...}`; `duration_ms` aracın kendi
çalışma süresidir (onay beklemesi dahil değil).
"""

from __future__ import annotations

import asyncio

from fusion_cli.core.hooks.events import HookEvent
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalAnswer, ApprovalMode, build_policy
from fusion_cli.engines.agent.hook_input import claude_tool_response
from fusion_cli.engines.agent.loop import AgentDeps, run_agent

from .fakes import RecordingSink, ScriptedProvider, make_config, model_result, tool_call
from .test_hooks_loop import _kayit_kancasi, _oturum, _Publisher, _satirlar, _tur, _yaz


def test_write_yaniti_yeni_dosyada_create_varolanda_update():
    girdi = {"file_path": "/p/a.txt", "content": "x"}
    yeni = claude_tool_response("write_file", girdi, "ok", existed=False)
    eski = claude_tool_response("write_file", girdi, "ok", existed=True)
    assert yeni["type"] == "create" and yeni["filePath"] == "/p/a.txt"
    assert eski["type"] == "update"


async def test_posttooluse_write_type_dosyanin_onceki_durumuna_gore(monkeypatch, tmp_path):
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(tmp_path, _kayit_kancasi(tmp_path, HookEvent.POST_TOOL_USE, kayit, "Write"))
    await _tur(monkeypatch, tmp_path, _yaz("a.txt", "1"), session)
    (tmp_path / "b.txt").write_text("eski", encoding="utf-8")
    oku = model_result(tool_calls=[tool_call("read_file", path="b.txt")])
    await _tur(monkeypatch, tmp_path, [oku, *_yaz("b.txt", "2")], session)
    turler = [satir["tool_response"]["type"] for satir in _satirlar(kayit)]
    assert turler == ["create", "update"]


class _YavasOnay:
    def __init__(self):
        self.soruldu = 0

    async def confirm(self, request):
        self.soruldu += 1
        await asyncio.sleep(0.6)
        return ApprovalAnswer.ONCE


async def test_duration_ms_onay_beklemesini_icermez(monkeypatch, tmp_path):
    kayit = tmp_path / "kayit.jsonl"
    session = _oturum(tmp_path, _kayit_kancasi(tmp_path, HookEvent.POST_TOOL_USE, kayit, "Write"))

    onay = _YavasOnay()
    provider = ScriptedProvider(_yaz("b.txt", "x"))
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kwargs: provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.SECURITY, onay),
        tool_context=ToolContext(root=tmp_path),
        hooks=session,
    )
    await run_agent("iş", deps)
    satirlar = _satirlar(kayit)
    assert onay.soruldu == 1 and len(satirlar) == 1
    assert satirlar[0]["duration_ms"] < 500


def test_mcp_server_kaynagi_yapilandirmadan(tmp_path):
    """Claude `mcp_server.source`: sunucu tanımının geldiği yer (#135)."""
    from types import SimpleNamespace

    from fusion_cli.config.models import McpScope
    from fusion_cli.engines.agent.hook_bridge import mcp_server_field

    config = SimpleNamespace(
        mcp_servers=(SimpleNamespace(name="plugin_x_db", scope=McpScope.PLUGIN),)
    )
    deps = SimpleNamespace(config=config)
    assert mcp_server_field("plugin_x_db", deps) == {"name": "plugin_x_db", "source": "plugin"}
    assert mcp_server_field("bilinmeyen", deps) == {"name": "bilinmeyen"}
    assert mcp_server_field("a", None) == {"name": "a"}

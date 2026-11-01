"""Uzun MCP çağrısının arka plana taşınması (#233): `CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS`.

Claude Code: ana sohbetteki MCP çağrısı 2 dk sonra arka plan görevine taşınır; sonuç
hazır olunca bildirilir. Alt ajanda çağrı beklenir.
"""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import pytest

from fusion_cli.core.tools import ToolContext, ToolResult
from fusion_cli.tools.mcp_background import McpBackgroundCalls, auto_background_s


def test_esik_ortam_degiskeni():
    assert auto_background_s({}) == 120.0
    assert auto_background_s({"CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": "1500"}) == 1.5
    assert auto_background_s({"CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": "0"}) is None
    assert auto_background_s({"CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS": "abc"}) == 120.0


def _context(tmp_path: Path) -> ToolContext:
    return ToolContext(root=tmp_path)


async def test_ana_sohbette_esigi_asan_cagri_arka_plana_tasinir_sonucu_bildirilir(tmp_path):
    calls = McpBackgroundCalls()
    context = _context(tmp_path)
    calls.mark_main(context)
    release = asyncio.Event()

    async def execute() -> ToolResult:
        await release.wait()
        return ToolResult(output="rapor hazır")

    moved = await calls.run(execute, context, "mcp__s__rapor", threshold_s=0.02)

    assert moved.ok
    assert "arka plan görevine taşındı" in moved.output
    assert calls.take_notices(context) == []
    release.set()
    await asyncio.sleep(0.01)
    notices = calls.take_notices(context)
    assert len(notices) == 1
    assert notices[0].harness_note
    assert "tamamlandı · mcp__s__rapor" in notices[0].content
    assert "rapor hazır" in notices[0].content
    assert calls.take_notices(context) == []


async def test_esik_altinda_biten_cagri_dogrudan_doner(tmp_path):
    calls = McpBackgroundCalls()
    context = _context(tmp_path)
    calls.mark_main(context)

    async def execute() -> ToolResult:
        return ToolResult(output="hızlı")

    assert (await calls.run(execute, context, "x", threshold_s=1)).output == "hızlı"
    assert calls.running == ()


async def test_alt_ajan_baglaminda_cagri_beklenir(tmp_path):
    calls = McpBackgroundCalls()
    main = _context(tmp_path)
    calls.mark_main(main)
    child = dataclasses.replace(main)

    async def execute() -> ToolResult:
        await asyncio.sleep(0.05)
        return ToolResult(output="tam sonuç")

    result = await calls.run(execute, child, "x", threshold_s=0.01)

    assert result.output == "tam sonuç"
    assert calls.take_notices(child) == []


async def test_kapali_esikte_tasima_yok(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS", "0")
    calls = McpBackgroundCalls()
    context = _context(tmp_path)
    calls.mark_main(context)

    async def execute() -> ToolResult:
        await asyncio.sleep(0.02)
        return ToolResult(output="bekledim")

    assert (await calls.run(execute, context, "x")).output == "bekledim"


async def test_basarisiz_arka_plan_cagrisi_bildirilir_ve_kapanista_iptal(tmp_path):
    calls = McpBackgroundCalls()
    context = _context(tmp_path)
    calls.mark_main(context)
    gate = asyncio.Event()

    async def fails() -> ToolResult:
        await gate.wait()
        raise RuntimeError("bağlantı koptu")

    async def hangs() -> ToolResult:
        await asyncio.Event().wait()
        return ToolResult(output="")

    await calls.run(fails, context, "a", threshold_s=0.01)
    await calls.run(hangs, context, "b", threshold_s=0.01)
    gate.set()
    await asyncio.sleep(0.01)
    notices = calls.take_notices(context)
    assert len(notices) == 1 and "başarısız" in notices[0].content
    assert "bağlantı koptu" in notices[0].content
    assert len(calls.running) == 1
    await calls.cancel_all()
    assert calls.running == ()


async def test_tur_iptali_beklenen_cagriyi_da_iptal_eder(tmp_path):
    calls = McpBackgroundCalls()
    context = _context(tmp_path)
    calls.mark_main(context)
    cancelled = asyncio.Event()

    async def execute() -> ToolResult:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return ToolResult(output="")

    waiter = asyncio.ensure_future(calls.run(execute, context, "x", threshold_s=5))
    await asyncio.sleep(0.01)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    await asyncio.sleep(0)
    assert cancelled.is_set()


async def test_motor_tasinan_cagrinin_sonucunu_sonraki_istege_ekler(monkeypatch, tmp_path):
    from fusion_cli.core.tools import Tool, ToolEffect
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
    from fusion_cli.engines.agent.loop import AgentDeps, run_agent
    from fusion_cli.tools.mcp_background import run_mcp_call

    from .fakes import (
        AlwaysApprove,
        RecordingSink,
        ScriptedProvider,
        make_config,
        model_result,
        tool_call,
    )

    monkeypatch.setenv("CLAUDE_CODE_MCP_AUTO_BACKGROUND_MS", "30")
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("mcp__s__rapor")]),
            model_result(tool_calls=[tool_call("mcp__s__bekle")]),
            model_result("Rapor arka planda tamamlandı; sonucu okudum ve doğruladım, tamam."),
        ]
    )
    monkeypatch.setattr(agent_loop, "build_provider", lambda *a, **k: provider)
    sink = RecordingSink()

    class _Pub:
        def publish(self, event):
            sink.handle(event)

    deps = AgentDeps(
        config=make_config(),
        publisher=_Pub(),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    async def _rapor_isi() -> ToolResult:
        await asyncio.sleep(0.1)
        return ToolResult(output="çeyrek raporu: 42")

    async def _rapor(args, context):
        return await run_mcp_call(_rapor_isi, context, "mcp__s__rapor")

    async def _bekle(args, context):
        await asyncio.sleep(0.2)
        return ToolResult(output="bekledim")

    for name, run in (("mcp__s__rapor", _rapor), ("mcp__s__bekle", _bekle)):
        deps.base_registry.register_or_replace(
            Tool(name=name, description=name, parameters={"type": "object"}, run=run,
                 effect=ToolEffect.LOCAL)
        )

    await run_agent("raporu al", deps, verify=False, self_review=False)

    ikinci = "\n".join(str(m.content) for m in provider.seen_messages[1])
    assert "arka plan görevine taşındı" in ikinci
    ucuncu = "\n".join(str(m.content) for m in provider.seen_messages[2])
    assert "tamamlandı · mcp__s__rapor" in ucuncu
    assert "çeyrek raporu: 42" in ucuncu

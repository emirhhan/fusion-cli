"""read_session ajan aracı."""

from __future__ import annotations

import json

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.engine_tools import build_agent_registry, build_history_tool
from fusion_cli.engines.agent.loop import AgentDeps

from .agent_harness import Publisher
from .fakes import AlwaysApprove, RecordingSink, make_config

# Not: pyproject'te `asyncio_mode = "auto"` — `@pytest.mark.asyncio` GEREKMEZ.


async def _hicbir_alt_ajan_calismaz(*args, **kwargs):
    raise AssertionError("bu testte alt-ajan çalıştırılmamalı")


def _minimal_deps(tmp_path, *, home):
    return AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        home=home,
    )


def test_home_yoksa_arac_kayit_defterinde_yok(tmp_path):
    deps = _minimal_deps(tmp_path, home=None)

    registry = build_agent_registry(deps, depth=0, run_agent=_hicbir_alt_ajan_calismaz)

    assert registry.get("read_session") is None


def test_home_varsa_arac_kayit_defterinde_var(tmp_path):
    deps = _minimal_deps(tmp_path, home=tmp_path)

    registry = build_agent_registry(deps, depth=0, run_agent=_hicbir_alt_ajan_calismaz)

    assert registry.get("read_session") is not None


def _claude_kur(home, mesajlar):
    hedef = home / ".claude" / "projects" / "-x"
    hedef.mkdir(parents=True, exist_ok=True)
    (hedef / "s1.jsonl").write_text(
        "\n".join(
            json.dumps({"type": "user", "message": {"role": "user", "content": m}})
            for m in mesajlar
        ),
        encoding="utf-8",
    )


async def test_arac_turlari_dondurur(tmp_path):
    _claude_kur(tmp_path, ["birinci", "ikinci"])
    tool = build_history_tool(tmp_path)

    sonuc = await tool.run({"source": "claude", "session_id": "s1"}, ToolContext(root=tmp_path))

    assert "birinci" in sonuc.output
    assert "ikinci" in sonuc.output


async def test_bilinmeyen_kaynak_hata_dondurur(tmp_path):
    _claude_kur(tmp_path, ["m"])
    tool = build_history_tool(tmp_path)

    sonuc = await tool.run({"source": "yok", "session_id": "s1"}, ToolContext(root=tmp_path))

    assert sonuc.ok is False


async def test_bilinmeyen_oturum_hata_dondurur(tmp_path):
    _claude_kur(tmp_path, ["m"])
    tool = build_history_tool(tmp_path)

    sonuc = await tool.run(
        {"source": "claude", "session_id": "olmayan"}, ToolContext(root=tmp_path)
    )

    assert sonuc.ok is False


async def test_imlec_gecirilir(tmp_path):
    _claude_kur(tmp_path, ["m0", "m1", "m2"])
    tool = build_history_tool(tmp_path)

    sonuc = await tool.run(
        {"source": "claude", "session_id": "s1", "cursor": 1, "limit": 1},
        ToolContext(root=tmp_path),
    )

    assert "m1" in sonuc.output
    assert "m0" not in sonuc.output

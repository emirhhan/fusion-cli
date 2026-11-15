"""autoCompactWindow ve experimental.cacheTtl frontmatter alanları (#23)."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team import SubTask, resolve_persona, run_subagent
from fusion_cli.tools.capabilities import CapabilityRegistry
from tests.agent_harness import Publisher
from tests.fakes import AlwaysApprove, RecordingSink, make_config


def _registry(root: Path, extra: str) -> CapabilityRegistry:
    folder = root / ".claude" / "agents"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "denetci.md").write_text(
        f"---\nname: denetci\ndescription: inceler\n{extra}---\nİncele.", encoding="utf-8"
    )
    return CapabilityRegistry(root / "ev", root)


def test_alanlar_okunur_ve_gecersiz_deger_yok_sayilir(tmp_path: Path, caplog) -> None:
    good = _registry(tmp_path / "a", "autoCompactWindow: 150000\nexperimental:\n  cacheTtl: 1h\n")
    with caplog.at_level(logging.WARNING):
        bad = _registry(tmp_path / "b", "autoCompactWindow: 50\nexperimental:\n  cacheTtl: 2h\n")

    persona = resolve_persona(good, "denetci")
    assert persona.auto_compact_window == 150_000 and persona.cache_ttl == "1h"
    wrong = resolve_persona(bad, "denetci")
    assert wrong.auto_compact_window == 0 and wrong.cache_ttl == ""


async def test_auto_compact_window_alt_ajanin_ozetleme_esigini_dusurur(tmp_path: Path) -> None:
    registry = _registry(tmp_path, "autoCompactWindow: 100000\n")
    deps = AgentDeps(
        config=make_config(),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        capabilities=registry,
    )
    seen: dict[str, object] = {}

    async def _agent(task, sub_deps, **kwargs):
        seen["chars"] = sub_deps.learned_compression_chars
        return SimpleNamespace(final_text="tamam", ok=True, tool_calls_made=0, messages=[])

    await run_subagent(deps, SubTask("iş", persona="denetci"), depth=0, run_agent=_agent)

    assert seen["chars"] == 150_000

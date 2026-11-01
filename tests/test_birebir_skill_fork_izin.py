"""`context: fork` becerisinin `allowed-tools` ön onayı yalnız alt ajana geçer (#141, #142).

Claude Code (skills, "Run skills in a subagent"): fork becerisi alt ajanda koşar; becerinin
araç kuralları o alt ajanın kapsamıdır. Ana model aynı turda onaysız `Bash` almamalı.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import skill_grants, skill_tool
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.engines.agent.team import SubTask
from fusion_cli.engines.agent.team_scope import derive_sub_context
from fusion_cli.tools.capabilities import CapabilityRegistry

from .fakes import make_config


def test_fork_becerisinin_on_onayi_ana_tura_girmez_alt_ajana_gecer(
    tmp_path: Path, monkeypatch
) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    folder = home / ".claude" / "skills" / "kos"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: kos\ncontext: fork\nbackground: false\nallowed-tools: Bash(*)\n---\nKoş: $ARGUMENTS",
        encoding="utf-8",
    )
    deps = SimpleNamespace(config=make_config(), approval_mode=lambda: ApprovalMode.AUTO, home=home)
    seen: dict[str, object] = {}

    async def fake_subagent(deps, subtask, *, depth, run_agent):  # type: ignore[no-untyped-def]
        seen["grants"] = subtask.skill_grants
        return SimpleNamespace(text="bitti")

    from fusion_cli.engines.agent import team

    monkeypatch.setattr(team, "run_subagent", fake_subagent)
    monkeypatch.setattr(team, "depth_limit_reached", lambda _deps, _depth: False)
    tool = skill_tool.build_skill_tool(
        CapabilityRegistry(home, root),
        deps,
        depth=0,
        run_agent=None,  # type: ignore[arg-type]
    )
    context = ToolContext(root=root)

    result = asyncio.run(tool.run({"skill": "kos", "args": "testler"}, context))

    assert result.output == "bitti"
    assert skill_grants.with_grants(None, context) is None  # ana model ön onay almaz
    assert ("allow", "Bash(*)") in seen["grants"]  # type: ignore[operator]


def test_alt_ajan_baglami_beceri_kurallarini_tasir(tmp_path: Path) -> None:
    parent = ToolContext(root=tmp_path)
    subtask = SubTask(task="iş", skill_grants=(("allow", "Bash(git *)"),))

    child = derive_sub_context(parent, subtask)

    assert child.skill_grants == [("allow", "Bash(git *)")]
    assert parent.skill_grants == []
    assert derive_sub_context(parent, SubTask(task="başka")).skill_grants == []

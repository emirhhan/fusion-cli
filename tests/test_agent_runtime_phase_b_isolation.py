"""Tanımdaki `isolation: worktree` alanı gerçek alt ajan koşusunda uygulanır (#22)."""

from __future__ import annotations

from types import SimpleNamespace

from fusion_cli.engines.agent import team
from fusion_cli.engines.agent.team import SubTask, run_subagent
from fusion_cli.tools.capabilities import CapabilityRegistry
from tests.test_team_fork import _deps as team_deps


def _agent(root, isolation: str) -> None:
    folder = root / ".claude" / "agents"
    folder.mkdir(parents=True, exist_ok=True)
    extra = f"isolation: {isolation}\n" if isolation else ""
    (folder / "yalitik.md").write_text(
        f"---\nname: yalitik\ndescription: ayrı ağaçta çalışır\n{extra}---\nÇalış.",
        encoding="utf-8",
    )


async def _launch(tmp_path, monkeypatch, isolation: str) -> list[str]:
    _agent(tmp_path, isolation)
    deps = team_deps(tmp_path)
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", tmp_path)
    opened: list[str] = []

    def enter(root, name):
        opened.append(name)
        return None

    async def run(task, child, **kwargs):
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    monkeypatch.setattr(team, "enter_worktree", enter)
    await run_subagent(deps, SubTask("yaz", persona="yalitik"), depth=0, run_agent=run)
    return opened


async def test_tanimdaki_worktree_yalitimi_gercek_kosuda_agac_acar(tmp_path, monkeypatch):
    assert len(await _launch(tmp_path, monkeypatch, "worktree")) == 1


async def test_yalitim_alani_yoksa_agac_acilmaz(tmp_path, monkeypatch):
    assert await _launch(tmp_path, monkeypatch, "") == []

"""EnterWorktree `path`, adsız ağaç ve ağaçtan ağaca geçiş (#342).

Claude Code (tools-reference › EnterWorktree; worktrees): `name` isteğe bağlıdır, `path` ile
deponun var olan bir ağacına geçilir, `.claude/worktrees` dışındaki yola girmeden önce sorulur;
oturumun yaratmadığı ağaç çıkışta kaldırılmaz.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from fusion_cli.cli.repl import worktrees
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core import worktree as core_worktree
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalRequest
from fusion_cli.engines.agent.worktree_approval import apply_worktree_path_policy
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.builtin import build_registry as build_tools
from fusion_cli.tools.worktree_tools import enter_worktree_tool, exit_worktree_tool

from .fakes import make_config


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "depo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fusion@test.local")
    _git(root, "config", "user.name", "Fusion Test")
    (root / "app.txt").write_text("taban\n", encoding="utf-8")
    _git(root, "add", "app.txt")
    _git(root, "commit", "-qm", "taban")
    return root


@pytest.fixture
def harici(repo: Path, tmp_path: Path) -> Path:
    path = tmp_path / "baska-yer"
    _git(repo, "worktree", "add", "-q", "-b", "elle", str(path))
    return path.resolve()


def _istek(args: dict, root: Path) -> tuple[ApprovalRequest, ToolContext]:
    tool = build_tools().get("enter_worktree")
    assert tool is not None
    return ApprovalRequest(tool=tool, args=args, danger=None), ToolContext(root=root)


def test_adsiz_cagri_rastgele_adla_agac_acar(repo):
    context = ToolContext(root=repo)
    result = asyncio.run(enter_worktree_tool({}, context))
    assert result.ok, result.output
    requested = context.worktree_switch.requested
    assert requested is not None and len(requested.name.split("-")) == 3
    assert requested.path.parent == (repo / ".claude" / "worktrees").resolve()


def test_path_ile_var_olan_agaca_gecilir_ve_cikista_kaldirilmaz(repo, harici, tmp_path):
    context = ToolContext(root=repo)
    result = asyncio.run(enter_worktree_tool({"path": str(harici)}, context))
    assert result.ok, result.output
    assert str(harici) in result.output
    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=repo,
        home=tmp_path / "ev",
    )
    worktrees.apply_switch(state, context)
    assert state.root == harici and state.worktree is not None and state.worktree.external

    ic = ToolContext(root=state.root)
    assert asyncio.run(exit_worktree_tool({}, ic)).ok and ic.worktree_switch.exit_requested
    bildirim = worktrees.apply_switch(state, ic)
    assert harici.is_dir(), "oturumun yaratmadığı ağaç kaldırılmaz"
    assert "yaratmadı" in bildirim and state.root == repo.resolve()


def test_path_depoya_ait_degilse_ya_da_ana_agacsa_reddedilir(repo, tmp_path):
    yabanci = tmp_path / "yabanci"
    yabanci.mkdir()
    context = ToolContext(root=repo)
    assert not asyncio.run(enter_worktree_tool({"path": str(yabanci)}, context)).ok
    assert not asyncio.run(enter_worktree_tool({"path": str(repo)}, context)).ok


def test_claude_worktrees_icindeki_yol_kunyesiyle_doner(repo):
    acilan = core_worktree.enter_worktree(repo, "kunyeli")
    context = ToolContext(root=repo)
    result = asyncio.run(enter_worktree_tool({"path": str(acilan.path)}, context))
    assert result.ok
    requested = context.worktree_switch.requested
    assert requested is not None and not requested.external and requested.name == "kunyeli"


def test_claude_worktrees_disindaki_yol_onay_ister(repo, harici):
    request, context = _istek({"path": str(harici)}, repo)
    assert apply_worktree_path_policy(request, context).pre_ask is not None
    ic = core_worktree.enter_worktree(repo, "ic")
    request, context = _istek({"path": str(ic.path)}, repo)
    assert apply_worktree_path_policy(request, context).pre_ask is None
    request, context = _istek({"name": "yeni"}, repo)
    assert apply_worktree_path_policy(request, context).pre_ask is None

"""Claude Code çalışma ağacı birebirliği: konum (#337) ve adsız `-w` (#339)."""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

import pytest

from fusion_cli.cli.worktree_argv import fill_missing_worktree_name
from fusion_cli.core import worktree as core_worktree
from fusion_cli.core.worktree_names import random_worktree_name


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
    (root / "a.txt").write_text("taban\n", encoding="utf-8")
    _git(root, "add", "a.txt")
    _git(root, "commit", "-qm", "taban")
    return root


def test_agac_claude_worktrees_altinda_ve_git_disinda(repo):
    tree = core_worktree.enter_worktree(repo, "ozellik")
    assert tree.path == repo / ".claude" / "worktrees" / "ozellik"
    assert tree.branch == "worktree-ozellik"
    exclude = (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8").splitlines()
    assert ".claude/worktrees/" in exclude and ".fusion/" in exclude
    assert _git(repo, "status", "--porcelain") == ""
    assert core_worktree.project_root_of(tree.path / "alt") == repo


def test_eski_fusion_worktrees_agaci_ilk_erisimde_tasinir(repo):
    legacy = repo / ".fusion" / "worktrees" / "eski"
    legacy.parent.mkdir(parents=True)
    _git(repo, "worktree", "add", "-q", "-b", "worktree-eski", str(legacy))
    (legacy / "is.txt").write_text("iş\n", encoding="utf-8")
    meta = repo / ".fusion" / "worktrees" / ".meta" / "eski.json"
    meta.parent.mkdir(parents=True)
    meta.write_text('{"branch": "worktree-eski", "base_commit": ""}', encoding="utf-8")

    tree = core_worktree.find_worktree(repo, "eski")

    assert tree is not None and tree.path == repo / ".claude" / "worktrees" / "eski"
    assert (tree.path / "is.txt").read_text(encoding="utf-8") == "iş\n"
    assert not legacy.exists()
    assert str(tree.path) in _git(repo, "worktree", "list")
    assert core_worktree.worktree_for_path(legacy.parent / "baska") is None


def test_eski_yoldaki_agacin_icinden_de_taninir(repo):
    legacy = repo / ".fusion" / "worktrees" / "x"
    assert core_worktree.project_root_of(legacy / "src") == repo


def test_rastgele_ad_claude_bicimi_ve_gecerli():
    ad = random_worktree_name(random.Random(1))
    assert len(ad.split("-")) == 3
    assert core_worktree.validate_name(ad) == ad


@pytest.mark.parametrize(
    ("argv", "beklenen"),
    [
        (["-w"], ["-w", "AD"]),
        (["--worktree"], ["--worktree", "AD"]),
        (["-w", "--name", "x"], ["-w", "AD", "--name", "x"]),
        (["agent", "-w", "-m", "auto", "görev"], ["agent", "-w", "AD", "-m", "auto", "görev"]),
        (["-w", "ozel"], ["-w", "ozel"]),
        (["--worktree=ozel"], ["--worktree=ozel"]),
        (["--", "-w"], ["--", "-w"]),
    ],
)
def test_adsiz_worktree_bayragina_ad_uretilir(argv, beklenen):
    assert fill_missing_worktree_name(argv, namer=lambda: "AD") == beklenen


@pytest.mark.parametrize(
    ("metin", "numara", "refspec"),
    [
        ("#12", 12, "pull/12/head"),
        ("https://github.com/o/r/pull/34", 34, "pull/34/head"),
        ("https://github.com/o/r/pull/34/files", 34, "pull/34/head"),
        ("https://gitlab.com/g/alt/r/-/merge_requests/5", 5, "merge-requests/5/head"),
    ],
)
def test_pr_mr_baglantisi_ayristirilir(metin, numara, refspec):
    from fusion_cli.core.worktree_pr import parse_pull_request

    ref = parse_pull_request(metin)
    assert ref is not None and (ref.number, ref.refspec) == (numara, refspec)
    assert ref.worktree_name == f"pr-{numara}"


def test_pr_numarasindan_agac_acilir(repo, tmp_path):
    """`--worktree "#7"`: origin'den pull/7/head çekilir, `.claude/worktrees/pr-7` açılır."""
    uzak = tmp_path / "uzak.git"
    _git(tmp_path, "clone", "-q", "--bare", str(repo), str(uzak))
    _git(repo, "checkout", "-q", "-b", "pr-dali")
    (repo / "pr.txt").write_text("pr işi\n", encoding="utf-8")
    _git(repo, "add", "pr.txt")
    _git(repo, "commit", "-qm", "pr")
    _git(repo, "push", "-q", str(uzak), "HEAD:refs/pull/7/head")
    _git(repo, "checkout", "-q", "-")
    _git(repo, "branch", "-q", "-D", "pr-dali")
    _git(repo, "remote", "add", "origin", str(uzak))

    tree = core_worktree.enter_worktree(repo, "#7")

    assert tree.name == "pr-7"
    assert tree.path == repo / ".claude" / "worktrees" / "pr-7"
    assert (tree.path / "pr.txt").read_text(encoding="utf-8") == "pr işi\n"
    assert core_worktree.enter_worktree(repo, "#7").path == tree.path  # ikinci kez aynı ağaç

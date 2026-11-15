"""`-w #N` / PR-MR adresi: PR origin'den çekilir, ağaç ondan dallanır (#314)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fusion_cli.cli.repl.worktrees import resolve_launch_root
from fusion_cli.cli.worktree_pr import parse_pull_ref
from fusion_cli.core.errors import WorktreeError


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.mark.parametrize(
    ("value", "number", "remote"),
    [
        ("#123", 123, "pull/123/head"),
        ("https://github.com/o/r/pull/45", 45, "pull/45/head"),
        ("https://gitlab.com/g/alt/r/-/merge_requests/9", 9, "merge-requests/9/head"),
    ],
)
def test_pr_degerleri_cozulur(value, number, remote):
    ref = parse_pull_ref(value)
    assert ref is not None and ref.number == number and ref.remote_ref == remote
    assert ref.worktree_name == f"pr-{number}"


def test_duz_ad_pr_sayilmaz():
    assert parse_pull_ref("ozellik") is None and parse_pull_ref("#abc") is None


def test_pr_numarasi_origin_den_cekilip_agac_acilir(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    (origin / "a.txt").write_text("ana", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-qm", "ana")
    _git(origin, "checkout", "-qb", "pr-dali")
    (origin / "a.txt").write_text("pr", encoding="utf-8")
    _git(origin, "commit", "-qam", "pr")
    pr_commit = _git(origin, "rev-parse", "HEAD")
    _git(origin, "update-ref", "refs/pull/7/head", pr_commit)
    _git(origin, "checkout", "-q", "main")
    clone = tmp_path / "klon"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    root, tree = resolve_launch_root(clone, "#7")
    assert tree is not None and tree.name == "pr-7"
    assert tree.base_commit == pr_commit
    assert (root / "a.txt").read_text(encoding="utf-8") == "pr"


def test_olmayan_pr_acik_git_hatasi(tmp_path):
    origin = tmp_path / "o"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    (origin / "x").write_text("1", encoding="utf-8")
    _git(origin, "add", ".")
    _git(origin, "commit", "-qm", "1")
    clone = tmp_path / "k"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    with pytest.raises(WorktreeError, match=r"çekilemedi|fetch"):
        resolve_launch_root(clone, "#99")

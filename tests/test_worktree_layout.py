"""Claude `worktree.symlinkDirectories` ve `worktree.sparsePaths` (#361).

Claude Code (settings-reference › worktree): ana depodaki dizinler ağaca bağ olarak konur;
sparsePaths ile ağaca yalnız listelenen dizinler (cone kipi) yazılır. Fusion'da ikisi de yoktu.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fusion_cli.config import worktree_settings
from fusion_cli.core import worktree as core_worktree
from fusion_cli.core.errors import WorktreeError
from fusion_cli.core.worktree_layout import WorktreeLayout


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "depo"
    for alt in ("src", "docs", "app"):
        (root / alt).mkdir(parents=True)
        (root / alt / "x.txt").write_text(alt, encoding="utf-8")
    (root / "kok.txt").write_text("kök\n", encoding="utf-8")
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (root / "node_modules" / "paket").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "fusion@test.local")
    _git(root, "config", "user.name", "Fusion Test")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "taban")
    return root


def test_symlink_dizini_ana_depoya_baglanir_ve_is_sayilmaz(repo):
    agac = core_worktree.enter_worktree(
        repo, "bagli", layout=WorktreeLayout(symlink_dirs=("node_modules", "yok"))
    )
    bag = agac.path / "node_modules"
    assert bag.is_symlink() and bag.resolve() == (repo / "node_modules").resolve()
    assert not (agac.path / "yok").exists()
    assert not core_worktree.is_dirty(agac)


def test_sparse_paths_yalniz_listelenen_dizinleri_yazar(repo):
    agac = core_worktree.enter_worktree(
        repo, "seyrek", layout=WorktreeLayout(sparse_paths=("src",))
    )
    assert (agac.path / "src" / "x.txt").exists()
    assert (agac.path / "kok.txt").exists()  # cone kipi kök dosyalarını tutar
    assert not (agac.path / "docs").exists() and not (agac.path / "app").exists()


def test_kok_disi_yol_reddedilir(repo):
    with pytest.raises(WorktreeError, match="göreli"):
        core_worktree.enter_worktree(repo, "kotu", layout=WorktreeLayout(symlink_dirs=("../x",)))


def test_ayarlar_claude_settings_jsondan_okunur_ve_birlesir(repo, tmp_path):
    home = tmp_path / "ev"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text(
        '{"worktree": {"symlinkDirectories": ["node_modules"], "sparsePaths": ["src"]}}',
        encoding="utf-8",
    )
    duzen = worktree_settings.worktree_layout(repo, home=home)
    assert duzen == WorktreeLayout(("node_modules",), ("src",))


def test_bag_kaynagi_depo_disina_cikan_sembolik_bagsa_atlanir(tmp_path):
    """`cache -> ~/.ssh` gibi depo dışını gösteren kaynak ağaca bağlanmaz (inceleme #10)."""
    from fusion_cli.core.worktree_layout import link_directories

    origin, agac, gizli = tmp_path / "depo", tmp_path / "agac", tmp_path / "gizli"
    for dizin in (origin, agac, gizli):
        dizin.mkdir()
    (origin / "cache").symlink_to(gizli, target_is_directory=True)
    (origin / "node_modules").mkdir()
    bagli = link_directories(origin, agac, ("cache", "node_modules"))
    assert bagli == (Path("node_modules"),)
    assert not (agac / "cache").exists()


def test_bag_hedefinin_ust_dizini_agac_disina_cikiyorsa_atlanir(tmp_path):
    from fusion_cli.core.worktree_layout import link_directories

    origin, agac, dis = tmp_path / "depo", tmp_path / "agac", tmp_path / "dis"
    for dizin in (origin / "paket" / "cache", agac, dis):
        dizin.mkdir(parents=True)
    (agac / "paket").symlink_to(dis, target_is_directory=True)
    assert link_directories(origin, agac, ("paket/cache",)) == ()
    assert not (dis / "cache").exists()

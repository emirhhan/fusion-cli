"""Çıkışta çalışma ağacı: temizse kendiliğinden silinir, iş varsa sakla/sil sorulur (#340).

Claude Code (worktrees › Clean up worktrees): değişiklik yoksa ağaç ve dalı silinir; değişiklik
ya da commit varsa sorulur; sakla → yeniden açma komutu, sil → ağaç ve dal commit'lerle gider.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fusion_cli.cli.repl import worktree_exit
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core import worktree as core_worktree
from fusion_cli.memory.factory import null_memory

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


def _oturum(repo: Path, tmp_path: Path, ad: str, *, adli: str = "") -> ReplState:
    worktree = core_worktree.enter_worktree(repo, ad)
    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=worktree.path,
        home=tmp_path / "ev",
        worktree=worktree,
    )
    state.conversation_name = adli
    return state


def _secici(cevap: str | None, sorular: list[str]):
    def secici(choices, title):
        sorular.append(title)
        return cevap

    return secici


def test_temiz_adsiz_oturum_sormadan_siler(repo, tmp_path):
    state = _oturum(repo, tmp_path, "temiz")
    sorular: list[str] = []
    satir = worktree_exit.finish_session_worktree(
        state, interactive=True, choose=_secici("sakla", sorular)
    )
    assert sorular == [] and "kaldırıldı" in satir
    assert not (repo / ".claude" / "worktrees" / "temiz").exists()


def test_is_varsa_sorulur_sakla_devam_komutunu_basar(repo, tmp_path):
    state = _oturum(repo, tmp_path, "isli")
    (state.root / "yeni.txt").write_text("iş\n", encoding="utf-8")
    sorular: list[str] = []
    satir = worktree_exit.finish_session_worktree(
        state, interactive=True, choose=_secici("sakla", sorular)
    )
    assert len(sorular) == 1 and "isli" in sorular[0]
    assert "fusion --worktree isli --resume session-" in satir
    assert (repo / ".claude" / "worktrees" / "isli").is_dir() and state.root == repo


def test_sil_secilince_commitli_dal_da_gider(repo, tmp_path):
    state = _oturum(repo, tmp_path, "commitli")
    (state.root / "b.txt").write_text("b\n", encoding="utf-8")
    _git(state.root, "add", "b.txt")
    _git(state.root, "commit", "-qm", "iş")
    satir = worktree_exit.finish_session_worktree(
        state, interactive=True, choose=_secici("sil", [])
    )
    assert "silindi" in satir
    assert not (repo / ".claude" / "worktrees" / "commitli").exists()
    assert _git(repo, "branch", "--list", "worktree-commitli") == ""


def test_adli_oturum_temiz_olsa_da_sorulur(repo, tmp_path):
    state = _oturum(repo, tmp_path, "adli", adli="giriş sayfası")
    sorular: list[str] = []
    worktree_exit.finish_session_worktree(state, interactive=True, choose=_secici(None, sorular))
    assert sorular and (repo / ".claude" / "worktrees" / "adli").is_dir()


def test_etkilesimsiz_cikista_eski_kural(repo, tmp_path):
    state = _oturum(repo, tmp_path, "boru")
    (state.root / "yeni.txt").write_text("iş\n", encoding="utf-8")
    satir = worktree_exit.finish_session_worktree(
        state, interactive=False, choose=_secici("sil", [])
    )
    assert "korundu" in satir and (repo / ".claude" / "worktrees" / "boru").is_dir()


async def test_oturum_icinde_girilen_agac_da_cikista_kapatilir(repo, tmp_path, monkeypatch):
    """`--worktree` olmadan, oturumda (`/worktree`, `enter_worktree`) girilen ağaç da çıkışta
    Claude kuralıyla kapanır (bağımsız inceleme #5)."""
    import io

    from rich.console import Console

    from fusion_cli.cli.repl import loop as repl_loop

    agac = core_worktree.enter_worktree(repo, "oturumda")
    kapatilan: list[str] = []

    async def surface(state, config, console, resume, setup_trigger=""):
        state.worktree = agac
        state.root = agac.path
        return 0

    def kapat(state, *, interactive, choose=None):
        kapatilan.append(state.worktree.name)
        return "kapandı"

    monkeypatch.setattr(repl_loop, "_run_surface", surface)
    monkeypatch.setattr(worktree_exit, "finish_session_worktree", kapat)
    sonuc = await repl_loop.run_repl(
        make_config(memory_dir=tmp_path / "memory"),
        memory=null_memory(),
        root=repo,
        console=Console(file=io.StringIO()),
    )
    assert sonuc == 0 and kapatilan == ["oturumda"]

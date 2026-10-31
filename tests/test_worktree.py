"""Git çalışma ağacı izolasyonu: çekirdek, `/worktree`, enter/exit araçları, alt ajan (P-037).

Ölçüldü (31 Ekim): depoda `git worktree` kullanımı yoktu; tek izolasyon plan motorunun
dizin kopyasıydı (`core/workspace.py`, `uses_worktree=False`).
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.appserver.commands import run_command
from fusion_cli.cli.repl import worktrees
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core import worktree as core_worktree
from fusion_cli.core.errors import WorktreeError
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.team import SubTask, _parse_subtask, derive_sub_context
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
    (root / ".env").write_text("GIZLI=1\n", encoding="utf-8")
    (root / ".worktreeinclude").write_text("# izlenmeyen ayarlar\n.env\n", encoding="utf-8")
    _git(root, "add", "app.txt", ".worktreeinclude")
    _git(root, "commit", "-qm", "taban")
    return root


# --- Çekirdek -------------------------------------------------------------------------- #


def test_create_worktree_dizin_dal_kunye_ve_include(repo):
    tree = core_worktree.enter_worktree(repo, "deneme")

    assert tree.path == repo / ".fusion" / "worktrees" / "deneme"
    assert tree.branch == "worktree-deneme"
    assert tree.base_commit == _git(repo, "rev-parse", "HEAD")
    assert _git(tree.path, "rev-parse", "--abbrev-ref", "HEAD") == "worktree-deneme"
    assert (tree.path / "app.txt").read_text(encoding="utf-8") == "taban\n"
    assert (tree.path / ".env").read_text(encoding="utf-8") == "GIZLI=1\n", ".worktreeinclude"
    assert ".fusion/" in (repo / ".git" / "info" / "exclude").read_text(encoding="utf-8")
    assert ".fusion" not in _git(repo, "status", "--porcelain"), "ana depo kirlenmez"
    assert core_worktree.find_worktree(repo, "deneme") == tree
    assert core_worktree.list_worktrees(repo) == (tree,)
    assert core_worktree.worktree_for_path(tree.path / "alt").name == "deneme"
    assert core_worktree.enter_worktree(tree.path, "deneme") == tree, "içinden tekrar girilir"


def test_worktreeinclude_kok_disi_desen_ve_symlink_kopyalanmaz(repo, tmp_path):
    """Ölçüldü (31 Ekim): `../outside.txt` deseni `.fusion/worktrees/outside.txt` olarak ağaç
    DIŞINA yazılıyor, `/etc/hosts`'a işaret eden symlink'in içeriği ağaçta düz dosya oluyordu.
    `.worktreeinclude` depoyla gelen güvenilmeyen bir dosyadır."""
    (tmp_path / "outside.txt").write_text("DIŞ SIR", encoding="utf-8")
    (repo / "baglanti.txt").symlink_to(tmp_path / "outside.txt")
    (repo / "ic").mkdir()
    (repo / "ic" / "ayar.local").write_text("IC=1", encoding="utf-8")
    (repo / "disa-dizin").symlink_to(tmp_path)
    (repo / ".worktreeinclude").write_text(
        "../outside.txt\n"
        f"{tmp_path / 'outside.txt'}\n"
        "baglanti.txt\n"
        "disa-dizin/outside.txt\n"
        "ic/*.local\n"
        ".env\n",
        encoding="utf-8",
    )

    tree = core_worktree.enter_worktree(repo, "guvenli")

    assert set(tree.included) == {"ic/ayar.local", ".env"}, tree.included
    assert not (repo / ".fusion" / "worktrees" / "outside.txt").exists(), "ağaç dışına yazıldı"
    assert not (tree.path / "baglanti.txt").exists(), "symlink hedefi kopyalandı"
    assert not (tree.path / "outside.txt").exists()
    assert not (tree.path / "disa-dizin").exists()
    assert (tree.path / "ic" / "ayar.local").read_text(encoding="utf-8") == "IC=1"


def test_gecersiz_ad_ve_git_disi_dizin_reddedilir(repo, tmp_path):
    for bad in ("../kacak", "a/b", "", ".."):
        with pytest.raises(WorktreeError):
            core_worktree.validate_name(bad)
    with pytest.raises(WorktreeError):
        core_worktree.enter_worktree(tmp_path / "gitsiz", "x")


def test_leave_temiz_agaci_kaldirir_kirli_ve_commitli_korur(repo):
    temiz = core_worktree.enter_worktree(repo, "temiz")
    assert core_worktree.leave_worktree(temiz).outcome is core_worktree.LeaveOutcome.REMOVED
    assert not temiz.path.exists()
    assert "worktree-temiz" not in _git(repo, "branch", "--list", "worktree-temiz")

    kirli = core_worktree.enter_worktree(repo, "kirli")
    (kirli.path / "yeni.txt").write_text("iş", encoding="utf-8")
    sonuc = core_worktree.leave_worktree(kirli)
    assert sonuc.outcome is core_worktree.LeaveOutcome.KEPT and sonuc.reason == "degisiklik"
    assert kirli.path.exists()

    commitli = core_worktree.enter_worktree(repo, "commitli")
    (commitli.path / "app.txt").write_text("değişti\n", encoding="utf-8")
    _git(commitli.path, "commit", "-qam", "iş")
    sonuc = core_worktree.leave_worktree(commitli)
    assert sonuc.outcome is core_worktree.LeaveOutcome.KEPT and sonuc.reason == "commit"
    core_worktree.remove_worktree(commitli, force=True)
    assert not commitli.path.exists()
    assert _git(repo, "branch", "--list", "worktree-commitli").strip(), "commit'li dal korunur"


# --- REPL `/worktree` ---------------------------------------------------------------- #


@pytest.fixture
def state(repo: Path, tmp_path: Path) -> ReplState:
    return ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=repo,
        home=tmp_path / "ev",
    )


def _run(state: ReplState, line: str) -> str:
    name, argument = parse(line)
    command = build_registry().get(name)
    assert command is not None, line
    return command.handler(state, argument)


def test_worktree_komutu_girer_listeler_cikar(state, repo):
    assert (
        _run(state, "/worktree") == "Kullanım: /worktree <ad>  ·  /worktree cik  ·  /worktree liste"
    )
    assert "yok" in _run(state, "/worktree liste")

    giris = _run(state, "/worktree ozellik")

    assert "Çalışma ağacı:" in giris and "worktree-ozellik" in giris
    assert state.root == repo / ".fusion" / "worktrees" / "ozellik"
    assert state.worktree is not None and state.worktree.origin == repo
    assert "ozellik" in _run(state, "/worktree")
    assert "worktree-ozellik" in _run(state, "/worktree liste")
    assert "önce /worktree cik" in _run(state, "/worktree baska")

    cikis = _run(state, "/worktree cik")

    assert "kaldırıldı" in cikis
    assert state.root == repo and state.worktree is None
    assert _run(state, "/worktree cik") == "Bir çalışma ağacında değilsin."


def test_worktree_cikista_is_kalmissa_korur_ve_yolu_soyler(state, repo):
    _run(state, "/worktree is")
    (state.root / "yeni.txt").write_text("x", encoding="utf-8")
    cikis = _run(state, "/worktree cik")
    assert "korundu" in cikis and "git merge worktree-is" in cikis
    assert state.root == repo


def test_masaustu_koprusu_worktree_calistirir(state, repo):
    sonuc = run_command(build_registry(), state, "worktree", "masa")
    assert sonuc["ok"] and "worktree-masa" in sonuc["metin"]
    assert state.root == repo / ".fusion" / "worktrees" / "masa"


# --- Ajan araçları ------------------------------------------------------------------- #


def test_enter_worktree_araci_kurar_ve_tur_sonunda_kok_degisir(state, repo):
    registry = build_tools()
    assert registry.get("enter_worktree") is not None and registry.get("exit_worktree") is not None
    context = ToolContext(root=repo)

    result = asyncio.run(enter_worktree_tool({"name": "ajan"}, context))

    assert result.ok, result.output
    assert ".fusion/worktrees/ajan" in result.output
    requested, exit_requested = (
        context.worktree_switch.requested,
        context.worktree_switch.exit_requested,
    )
    assert requested is not None and not exit_requested
    bildirim = worktrees.apply_switch(state, context)
    assert "geçti" in bildirim and state.root == requested.path
    assert context.worktree_switch.requested is None, "istek bir kez uygulanır"

    ic = ToolContext(root=state.root)
    assert not asyncio.run(enter_worktree_tool({"name": "icice"}, ic)).ok, "iç içe ağaç açılmaz"
    cikis = asyncio.run(exit_worktree_tool({}, ic))
    assert cikis.ok and ic.worktree_switch.exit_requested
    assert "kaldırıldı" in worktrees.apply_switch(state, ic)
    assert state.root == repo


def test_exit_worktree_agacta_degilken_bilgi_verir(repo):
    context = ToolContext(root=repo)
    result = asyncio.run(exit_worktree_tool({}, context))
    assert result.ok and not context.worktree_switch.exit_requested
    assert not asyncio.run(enter_worktree_tool({"name": ""}, context)).ok


# --- Alt ajan izolasyonu ---------------------------------------------------------------- #


def test_alt_ajan_izolasyon_worktree_ayri_kok_ve_degisiklik_kumesi(repo):
    parsed = _parse_subtask({"task": "iş", "izolasyon": "worktree"})
    assert isinstance(parsed, SubTask) and parsed.isolation == "worktree"
    assert isinstance(_parse_subtask({"task": "iş", "izolasyon": "kopya"}), str)

    tree = core_worktree.enter_worktree(repo, "ajan-test")
    parent = ToolContext(root=repo)
    child = derive_sub_context(parent, parsed, root=tree.path)

    assert child.root == tree.path
    assert child.changes is not parent.changes, "üyenin kaydı ana projenin /undo'suna karışmaz"
    assert child.write_scope is None


def test_worktree_araclari_yalniz_ilgili_istekte_sunulur():
    """Ölçüldü (31 Ekim): iki aracın şeması emülasyon istem bütçesini (11.400) aşıyordu."""
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.expertise import is_worktree_task
    from fusion_cli.engines.agent.loop import SCOPED_TOOLS, _permitted

    registry = build_tools()
    sirada = _permitted(None, registry, ExecutionPolicy(is_web=False))
    assert sirada is not None and "enter_worktree" not in sirada
    acik = _permitted(None, registry, ExecutionPolicy(is_web=False), frozenset({"worktree"}))
    assert acik is not None and {"enter_worktree", "exit_worktree"} <= acik
    assert SCOPED_TOOLS["enter_worktree"] == "worktree"
    assert is_worktree_task("bunu ayrı bir dalda, worktree içinde dene")
    assert is_worktree_task("izole bir dalda çalış, ana projeye dokunma")
    assert not is_worktree_task("CSS arka plan rengini değiştir")


# --- CLI ---------------------------------------------------------------------------------- #


def test_cli_worktree_gitsiz_dizinde_hata_ile_cikar(tmp_path, monkeypatch):
    from fusion_cli.cli import app as app_module

    monkeypatch.setattr(app_module, "load_config", lambda: make_config(memory_dir=tmp_path / "m"))
    monkeypatch.setattr(app_module, "evaluate", lambda *_a, **_k: type("R", (), {"state": None})())
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app_module.app, ["--worktree", "x"])

    assert result.exit_code == 1
    assert "git deposu değil" in (result.stderr or "") + result.stdout

"""`WorktreeCreate` / `WorktreeRemove` kancaları (#90): git yerine kanca ağacı kurar."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

from fusion_cli.cli.repl import worktrees
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core import worktree as core_worktree
from fusion_cli.core.errors import WorktreeError
from fusion_cli.core.hooks.decision import verdict_from_run
from fusion_cli.core.hooks.events import CLAUDE_ONLY_EVENTS, HookEvent, HookRun, HookSet
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.engines.hooks.worktree_hooks import worktree_hook_calls
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.worktree_tools import enter_worktree_tool

from .fakes import make_config


def _script(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return f"{sys.executable} {path}"


def _create_body(log: Path, base: Path, *, exit_code: int = 0, print_path: bool = True) -> str:
    return (
        "import json, sys, pathlib\n"
        "data = json.load(sys.stdin)\n"
        f"open(r'{log}', 'w').write(json.dumps(data))\n"
        f"target = pathlib.Path(r'{base}') / data['name']\n"
        "target.mkdir(parents=True, exist_ok=True)\n"
        + ("print(target)\n" if print_path else "")
        + (f"sys.exit({exit_code})\n" if exit_code else "")
    )


def _remove_body(log: Path) -> str:
    return (
        "import json, sys, shutil\n"
        "data = json.load(sys.stdin)\n"
        f"open(r'{log}', 'w').write(json.dumps(data))\n"
        "shutil.rmtree(data['worktree_path'], ignore_errors=True)\n"
    )


def _session(root: Path, block: dict[str, object]) -> HookSession:
    commands, skipped = parse_hooks_block(block, source="kullanici", path=Path("settings.json"))
    assert not skipped
    return HookSession(root=root, loader=lambda: HookSet(commands))


def _hooks(tmp_path: Path, *, create: str | None = None, remove: str | None = None) -> dict:
    block: dict[str, object] = {}
    if create is not None:
        block["WorktreeCreate"] = [{"hooks": [{"type": "command", "command": create}]}]
    if remove is not None:
        block["WorktreeRemove"] = [{"hooks": [{"type": "command", "command": remove}]}]
    return block


def test_olaylar_artik_tetikleniyor():
    for name in ("WorktreeCreate", "WorktreeRemove", "Setup"):
        assert name not in CLAUDE_ONLY_EVENTS


def test_kanca_git_disi_klasorde_agac_kurar_ve_yolu_kullanilir(tmp_path):
    project = tmp_path / "proje"
    project.mkdir()
    log, base = tmp_path / "girdi.json", tmp_path / "agaclar"
    session = _session(
        project, _hooks(tmp_path, create=_script(tmp_path, "c", _create_body(log, base)))
    )

    tree = core_worktree.enter_worktree(project, "ozellik", hooks=worktree_hook_calls(session))

    assert tree.hooked is True
    assert tree.path == (base / "ozellik").resolve()
    assert tree.branch == ""
    payload = json.loads(log.read_text())
    assert payload["hook_event_name"] == "WorktreeCreate"
    assert payload["name"] == "ozellik"
    assert not (project / ".fusion").exists()  # git yolu hiç çalışmadı


def test_kanca_yoksa_git_yolu_degismez(tmp_path):
    project = tmp_path / "proje"
    project.mkdir()
    session = _session(project, {})
    with pytest.raises(WorktreeError, match="git deposu değil"):
        core_worktree.enter_worktree(project, "x", hooks=worktree_hook_calls(session))


@pytest.mark.parametrize(
    ("exit_code", "print_path", "match"),
    [(1, True, "oluşturamadı"), (0, False, "yolunu yazmadı")],
)
def test_sifir_disi_cikis_ya_da_yolsuz_cikti_kurulumu_bozar(tmp_path, exit_code, print_path, match):
    project = tmp_path / "proje"
    project.mkdir()
    body = _create_body(
        tmp_path / "g.json", tmp_path / "a", exit_code=exit_code, print_path=print_path
    )
    session = _session(project, _hooks(tmp_path, create=_script(tmp_path, "c", body)))
    with pytest.raises(WorktreeError, match=match):
        core_worktree.enter_worktree(project, "x", hooks=worktree_hook_calls(session))


def test_http_kancasi_worktree_path_alanini_verir():
    command = parse_hooks_block(
        {"WorktreeCreate": [{"hooks": [{"type": "http", "url": "http://127.0.0.1:1/x"}]}]},
        source="kullanici",
        path=Path("settings.json"),
    )[0][0]
    body = {"hookSpecificOutput": {"hookEventName": "WorktreeCreate", "worktreePath": "/tmp/a"}}
    run = HookRun(command, 0, stdout=json.dumps(body))
    assert verdict_from_run(HookEvent.WORKTREE_CREATE, run).worktree_path == "/tmp/a"


def test_kanca_agacini_worktree_remove_kaldirir_yoksa_korunur(tmp_path):
    project = tmp_path / "proje"
    project.mkdir()
    create = _script(tmp_path, "c", _create_body(tmp_path / "c.json", tmp_path / "a"))
    remove_log = tmp_path / "r.json"
    remove = _script(tmp_path, "r", _remove_body(remove_log))

    only_create = _session(project, _hooks(tmp_path, create=create))
    tree = core_worktree.enter_worktree(project, "bir", hooks=worktree_hook_calls(only_create))
    kept = core_worktree.leave_worktree(tree, hooks=worktree_hook_calls(only_create))
    assert kept.outcome is core_worktree.LeaveOutcome.KEPT
    assert kept.reason == "kanca"
    assert tree.path.is_dir()

    both = _session(project, _hooks(tmp_path, create=create, remove=remove))
    removed = core_worktree.leave_worktree(tree, hooks=worktree_hook_calls(both))
    assert removed.outcome is core_worktree.LeaveOutcome.REMOVED
    assert json.loads(remove_log.read_text())["worktree_path"] == str(tree.path)
    assert not tree.path.exists()


def _git_repo(tmp_path: Path) -> Path:
    root = tmp_path / "depo"
    root.mkdir()
    for args in (
        ("init", "-q"),
        ("config", "user.email", "fusion@test.local"),
        ("config", "user.name", "Fusion Test"),
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    (root / "a.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "t"], cwd=root, check=True, capture_output=True)
    return root


def test_git_agaci_kaldirilinca_worktree_remove_temizlik_icin_tetiklenir(tmp_path):
    repo = _git_repo(tmp_path)
    log = tmp_path / "r.json"
    session = _session(repo, _hooks(tmp_path, remove=_script(tmp_path, "r", _remove_body(log))))
    calls = worktree_hook_calls(session)
    tree = core_worktree.enter_worktree(repo, "temiz", hooks=calls)
    assert tree.hooked is False
    result = core_worktree.leave_worktree(tree, hooks=calls)
    assert result.outcome is core_worktree.LeaveOutcome.REMOVED
    assert json.loads(log.read_text())["worktree_path"] == str(tree.path)


def test_repl_worktree_komutu_calisan_dongu_icinden_kancayi_calistirir(tmp_path):
    project = tmp_path / "proje"
    project.mkdir()
    log, base = tmp_path / "g.json", tmp_path / "a"
    session = _session(
        project, _hooks(tmp_path, create=_script(tmp_path, "c", _create_body(log, base)))
    )
    state = ReplState(
        config=make_config(), memory=null_memory(), root=project, home=tmp_path / "ev"
    )
    state.hook_session = session

    async def run() -> str:
        return worktrees.worktree_command(state, "deneme")

    text = asyncio.run(run())
    assert "WorktreeCreate" in text
    assert state.root == (base / "deneme").resolve()
    assert state.worktree is not None and state.worktree.hooked


def test_enter_worktree_araci_turun_kancasini_kullanir(tmp_path):
    project = tmp_path / "proje"
    project.mkdir()
    base = tmp_path / "a"
    session = _session(
        project,
        _hooks(tmp_path, create=_script(tmp_path, "c", _create_body(tmp_path / "g.json", base))),
    )
    context = ToolContext(root=project)
    context.worktree_switch.hooks = worktree_hook_calls(session)

    result = asyncio.run(enter_worktree_tool({"name": "arac"}, context))

    assert result.ok, result.output
    requested, _ = context.worktree_switch.take()
    assert requested is not None and requested.path == (base / "arac").resolve()


def test_setup_olayi_http_turunu_desteklemez():
    _commands, skipped = parse_hooks_block(
        {"Setup": [{"matcher": "init", "hooks": [{"type": "http", "url": "http://127.0.0.1/x"}]}]},
        source="kullanici",
        path=Path("settings.json"),
    )
    assert skipped and "desteklemez" in skipped[0].reason

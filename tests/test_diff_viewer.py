"""`/diff` etkileşimli görüntüleyici (#230): git farkı ↔ turlar (←/→), Enter dosya farkı."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from fusion_cli.cli.repl import diff_viewer
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    root = tmp_path / "depo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "a.txt").write_text("bir\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "ilk")
    return ReplState(config=make_config(), memory=null_memory(), root=root, home=tmp_path)


def _turn(state: ReplState, task: str, path: Path, text: str) -> None:
    checkpoint = state.checkpoints.begin(task, state.history)
    checkpoint.changes.record(path)
    path.write_text(text, encoding="utf-8")
    checkpoint.changes.record_applied(path)


def test_gorunumler_git_ve_turlar(state: ReplState) -> None:
    dosya = state.root / "a.txt"
    _turn(state, "ilk değişiklik", dosya, "iki\n")
    _turn(state, "ikinci değişiklik", dosya, "üç\n")
    views = diff_viewer.views(state)
    assert [view.title.split(":")[0] for view in views] == [
        "Git çalışma ağacı (git diff HEAD)",
        "Tur 1",
        "Tur 2",
    ]
    assert views[0].files == ("a.txt",)
    birinci = views[1].diff_of("a.txt")
    assert "-bir" in birinci and "+iki" in birinci and "+üç" not in birinci
    ikinci = views[2].diff_of("a.txt")
    assert "-iki" in ikinci and "+üç" in ikinci


async def test_surucu_oklarla_gezer_enter_dosya_farki(state: ReplState) -> None:
    _turn(state, "değiştir", state.root / "a.txt", "iki\n")
    answers = iter(["right:dosya:a.txt", "dosya:a.txt", None, "left:dosya:a.txt", None])
    titles: list[str] = []
    rows_seen: list[list[str]] = []

    async def ask(title, rows, keys, initial):
        titles.append(title)
        rows_seen.append([row.label for row in rows])
        return next(answers)

    assert await diff_viewer.run_async(state, ask)
    assert "1/2" in titles[0] and "2/2 · Tur 1" in titles[1]
    assert titles[2] == "a.txt" and "+iki" in rows_seen[2]
    assert "1/2" in titles[4]


async def test_gosterecek_yoksa_false(tmp_path: Path) -> None:
    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)

    async def ask(*_a):
        raise AssertionError("açılmamalı")

    assert await diff_viewer.run_async(state, ask) is False


async def test_tui_diff_goruntuleyiciyi_acar(state: ReplState) -> None:
    from fusion_cli.cli.repl.tui_loop import _TuiSession

    (state.root / "a.txt").write_text("değişti\n", encoding="utf-8")
    session = _TuiSession(state)
    task = asyncio.ensure_future(session._command("/diff"))
    for _ in range(50):
        await asyncio.sleep(0.02)
        if session.tui._mode == "choice":
            break
    assert "/diff 1/1" in session.tui._choice_title
    assert session.tui._choice_alt_keys == ("left", "right")
    session.tui._resolve(None)
    await task


def test_git_gorunumu_turkce_ve_yeniden_adlandirilmis_dosya_farkini_acar(state: ReplState) -> None:
    # `core.quotepath` açıkken numstat Türkçe adı tırnaklı sekizlik kaçışla verir; ad pathspec
    # olarak aynen kullanılırsa fark boş gelir. Yeniden adlandırma `old => new` biçimindedir.
    (state.root / "türkçe.txt").write_text("eski\n", encoding="utf-8")
    (state.root / "yildiz[1].txt").write_text("x\n", encoding="utf-8")
    _git(state.root, "add", ".")
    _git(state.root, "commit", "-qm", "iki")
    _git(state.root, "config", "core.quotepath", "true")
    (state.root / "türkçe.txt").write_text("yeni\n", encoding="utf-8")
    (state.root / "yildiz[1].txt").write_text("y\n", encoding="utf-8")
    _git(state.root, "mv", "a.txt", "b.txt")
    view = diff_viewer.views(state)[0]
    assert set(view.files) == {"türkçe.txt", "yildiz[1].txt", "a.txt", "b.txt"}
    assert "+yeni" in view.diff_of("türkçe.txt")
    assert "+y" in view.diff_of("yildiz[1].txt")
    assert "-bir" in view.diff_of("a.txt")
    assert "+bir" in view.diff_of("b.txt")

"""Claude Code oturum seçicisi (#202): dal/boyut sütunları, Space önizleme, Ctrl+R ad,
Ctrl+A bütün projeler, Ctrl+W bütün çalışma ağaçları, Ctrl+B geçerli dal."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fusion_cli.cli.repl import resume_picker
from fusion_cli.cli.repl.transcript_store import (
    TranscriptStore,
    current_git_branch,
    list_conversations,
)


def _repo(path: Path, branch: str) -> Path:
    (path / ".git").mkdir(parents=True)
    (path / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    return path


def _sohbet(memory: Path, root: Path, cid: str, text: str) -> None:
    store = TranscriptStore(memory, root, conversation_id=cid)
    store.record_user(text)
    store.record_assistant(f"cevap {text}")


@pytest.fixture
def ortam(tmp_path: Path) -> tuple[Path, Path]:
    memory = tmp_path / "bellek"
    root = _repo(tmp_path / "proje", "main")
    return memory, root


def test_dal_ve_boyut_kaydedilir_satirda_gorunur(ortam) -> None:
    memory, root = ortam
    _sohbet(memory, root, "s-1", "giriş hatası")
    ref = list_conversations(memory, root)[0]
    assert ref.git_branch == "main" and ref.cwd == str(root.resolve()) and ref.size_bytes > 0
    rows = resume_picker.rows(memory, root, resume_picker.PickerView())
    choice = resume_picker.choices(rows)[0]
    assert "main" in choice.description and "B" in choice.description
    assert "2 mesaj" in choice.description


def test_worktree_dosyasi_gitdir_ile_dal_okunur(tmp_path: Path) -> None:
    gitdir = tmp_path / "ana" / ".git" / "worktrees" / "x"
    gitdir.mkdir(parents=True)
    (gitdir / "HEAD").write_text("ref: refs/heads/feat/x\n", encoding="utf-8")
    tree = tmp_path / "agac"
    tree.mkdir()
    (tree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    assert current_git_branch(tree / "alt") == "feat/x" or current_git_branch(tree) == "feat/x"
    (gitdir / "HEAD").write_text("0123abcd\n", encoding="utf-8")
    assert current_git_branch(tree) == ""


def test_kapsam_ve_dal_suzgecleri(ortam, tmp_path: Path) -> None:
    memory, root = ortam
    _sohbet(memory, root, "s-ana", "ana dalda")
    (root / ".git" / "HEAD").write_text("ref: refs/heads/feat\n", encoding="utf-8")
    _sohbet(memory, root, "s-feat", "feat dalında")
    alt = root / ".fusion" / "worktrees" / "deneme"
    alt.mkdir(parents=True)
    _sohbet(memory, alt, "s-alt", "çalışma ağacında")
    baska = _repo(tmp_path / "baska", "main")
    _sohbet(memory, baska, "s-baska", "başka proje")

    def ids(view):
        return {row.ref.conversation_id for row in resume_picker.rows(memory, root, view)}

    view = resume_picker.PickerView()
    assert ids(view) == {"s-ana", "s-feat"}
    assert ids(view.toggled("c-w")) == {"s-ana", "s-feat", "s-alt"}
    assert ids(view.toggled("c-a")) == {"s-ana", "s-feat", "s-alt", "s-baska"}
    assert ids(view.toggled("c-b")) == {"s-feat"}
    assert "bütün projeler" in resume_picker.title(view.toggled("c-a"))


def test_surucu_onizler_adlandirir_ve_secer(ortam) -> None:
    memory, root = ortam
    _sohbet(memory, root, "s-1", "ilk istem")
    answers = iter(["space:s-1", None, "c-r:s-1", "c-a:s-1", "s-1"])
    titles: list[str] = []
    initials: list[str] = []

    def ask(title, rows, keys, initial):
        titles.append(title)
        initials.append(initial)
        if title.startswith("Önizleme"):
            assert any("ilk istem" in row.label for row in rows)
        return next(answers)

    chosen = resume_picker.run(memory, root, ask, lambda: "Yeni ad")
    assert chosen == "s-1"
    assert titles[1].startswith("Önizleme")
    assert initials[2] == "s-1"
    assert "bütün projeler" in titles[-1]
    assert list_conversations(memory, root)[0].name == "Yeni ad"


async def test_tui_seciciyi_ozel_tuslarla_acar(ortam, tmp_path: Path) -> None:
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.cli.repl.tui_loop import _TuiSession
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    memory, root = ortam
    state = ReplState(
        config=make_config(memory_dir=memory), memory=null_memory(), root=root, home=tmp_path
    )
    _sohbet(memory, root, "s-1", "ilk istem")
    session = _TuiSession(state)
    task = asyncio.ensure_future(session._resolve_own_resume())
    await asyncio.sleep(0.01)
    assert session.tui._choice_alt_keys == resume_picker.KEYS
    session.tui._pick_alt("c-b")
    await asyncio.sleep(0.01)
    assert "yalnız bu dal" in session.tui._choice_title
    session.tui._resolve("s-1")
    assert await task == "s-1"


def test_satir_ici_secici_arama_gorunumu() -> None:
    """Satır içi seçicide yazarak arama (#202): süzme, başlıkta sorgu, Esc önce aramadan çıkar."""
    from fusion_cli.ui.picker import Choice, PickerState, SearchView

    rows = [Choice("a", "giriş hatası", "main"), Choice("b", "README", "feat/x")]
    view = SearchView(rows, searchable=True)
    state = PickerState(2, 1)
    assert not view.type("j", state)  # gezinme tuşu arama başlatmaz
    assert view.type("f", state) and [c.value for c in view.rows()] == ["b"]
    assert state.index == 0 and view.title("Başlık") == "Başlık  / f"
    assert view.type_if_active("j", None, state) and view.rows() == []
    assert view.leave(state) and len(view.rows()) == 2 and not view.leave(state)
    assert SearchView(rows, searchable=False).type("f", state) is False


def test_dallar_kok_oturumun_altinda_gruplanir(ortam) -> None:
    """Claude Code: /branch ve --fork-session kopyaları kök oturumun altında (#202)."""
    from fusion_cli.cli.repl.session_resume import fork_conversation
    from fusion_cli.core.types import Message

    memory, root = ortam
    _sohbet(memory, root, "s-kok", "kök istem")
    fork_conversation(
        memory,
        root,
        [Message("user", "kök istem"), Message("assistant", "cevap")],
        target_id="s-dal",
        source_id="s-kok",
    )
    _sohbet(memory, root, "s-yeni", "en yeni")
    found = resume_picker.rows(memory, root, resume_picker.PickerView())
    assert [row.ref.conversation_id for row in found] == ["s-yeni", "s-kok", "s-dal"]
    labels = {c.value: c.label for c in resume_picker.choices(found)}
    assert labels["s-dal"].startswith("  ↳ ") and not labels["s-kok"].startswith(" ")

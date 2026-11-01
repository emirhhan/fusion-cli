"""`DirectoryAdded` kancası (#213): `/add-dir` başarıyla bir dizin ekleyince tetiklenir.

Claude Code: olay `directory` ve `source` (`slash_command`) alanlarıyla gelir, eşleştirici
kaynağa bakar, engelleyemez; zaten çalışma dizini olan ya da içindeki dizinde tetiklenmez.
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from fusion_cli.cli.repl import hook_events
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import CLAUDE_ONLY_EVENTS, HookCommand, HookEvent, HookSet
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture
def ev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "ev"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("FUSION_HOOKS", raising=False)
    return home


def _kanca(tmp_path: Path, kayit: Path, matcher: str = "") -> HookCommand:
    script = tmp_path / "dizin_kanca.py"
    script.write_text(
        "import sys\n"
        f"open({str(kayit)!r}, 'a', encoding='utf-8').write(sys.stdin.read().strip() + '\\n')\n",
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    return HookCommand(HookEvent.DIRECTORY_ADDED, matcher, command, 20.0, "test", "")


def _durum(root: Path, home: Path, *commands: HookCommand) -> ReplState:
    state = ReplState(config=make_config(), memory=null_memory(), root=root, home=home)
    state.hook_session = HookSession(root=root, loader=lambda: HookSet(tuple(commands)))
    return state


def _satirlar(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_directoryadded_tanimi_artik_atlanmaz() -> None:
    assert "DirectoryAdded" not in CLAUDE_ONLY_EVENTS
    commands, skipped = parse_hooks_block(
        {
            "DirectoryAdded": [
                {"matcher": "slash_command", "hooks": [{"type": "command", "command": "x"}]}
            ]
        },
        source="fusion",
        path=Path("hooks.json"),
        default_timeout_s=60.0,
    )
    assert [c.event for c in commands] == [HookEvent.DIRECTORY_ADDED] and skipped == ()


async def test_add_dir_kancayi_dizin_ve_kaynakla_tetikler(tmp_path: Path, ev: Path) -> None:
    kok, ek = tmp_path / "proje", tmp_path / "diger"
    kok.mkdir()
    ek.mkdir()
    kayit = tmp_path / "kayit.jsonl"
    state = _durum(kok, ev, _kanca(tmp_path, kayit, "slash_command"))

    build_registry().get("add-dir").handler(state, str(ek))  # type: ignore[union-attr]
    await hook_events.flush(state)

    satirlar = _satirlar(kayit)
    assert len(satirlar) == 1
    assert satirlar[0]["hook_event_name"] == "DirectoryAdded"
    assert satirlar[0]["directory"] == str(ek.resolve())
    assert satirlar[0]["source"] == "slash_command"


async def test_kok_icindeki_dizinde_tetiklenmez(tmp_path: Path, ev: Path) -> None:
    kok = tmp_path / "proje"
    (kok / "alt").mkdir(parents=True)
    kayit = tmp_path / "kayit.jsonl"
    state = _durum(kok, ev, _kanca(tmp_path, kayit))

    build_registry().get("add-dir").handler(state, str(kok / "alt"))  # type: ignore[union-attr]
    await hook_events.flush(state)

    assert _satirlar(kayit) == []


async def test_baska_kaynak_eslestiricisi_tetiklenmez(tmp_path: Path, ev: Path) -> None:
    kok, ek = tmp_path / "proje", tmp_path / "diger"
    kok.mkdir()
    ek.mkdir()
    kayit = tmp_path / "kayit.jsonl"
    state = _durum(kok, ev, _kanca(tmp_path, kayit, "register_repo_root"))

    build_registry().get("add-dir").handler(state, str(ek))  # type: ignore[union-attr]
    await hook_events.flush(state)

    assert _satirlar(kayit) == []


async def test_kanca_additionalcontext_sonraki_tura_baglam_olur(tmp_path: Path, ev: Path) -> None:
    """Kanca `additionalContext`'i kullanıcıya basılmaz, modele bağlam olarak gider (#213)."""
    kok, ek = tmp_path / "proje", tmp_path / "diger"
    kok.mkdir()
    ek.mkdir()
    script = tmp_path / "baglam.py"
    script.write_text(
        "import json\n"
        "print(json.dumps({'systemMessage': 'eklendi', 'hookSpecificOutput': "
        "{'hookEventName': 'DirectoryAdded', 'additionalContext': 'yeni dizin notu'}}))\n",
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    state = _durum(kok, ev, HookCommand(HookEvent.DIRECTORY_ADDED, "", command, 20.0, "test", ""))

    build_registry().get("add-dir").handler(state, str(ek))  # type: ignore[union-attr]
    lines = await hook_events.flush(state)

    assert any("eklendi" in line for line in lines)
    assert not any("yeni dizin notu" in line for line in lines)
    assert any("yeni dizin notu" in block for block in state.pending_blocks)

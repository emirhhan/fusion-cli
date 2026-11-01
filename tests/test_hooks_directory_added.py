"""`DirectoryAdded` kancası (#90): `/add-dir` sonrası arka planda, systemMessage modele."""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
from pathlib import Path

import pytest

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.workspace_commands import add_dir
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import CLAUDE_ONLY_EVENTS, HookCommand, HookEvent, HookSet
from fusion_cli.engines.agent.hook_directory import directory_added
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _session(tmp_path: Path, matcher: str = "slash_command") -> tuple[HookSession, Path]:
    log = tmp_path / "girdi.json"
    script = tmp_path / "kanca.py"
    script.write_text(
        f"import sys\nopen(r'{log}', 'w').write(sys.stdin.read())\n"
        'print(\'{"systemMessage": "bağımlılıklar kuruldu", "continue": false}\')\n',
        encoding="utf-8",
    )
    commands, skipped = parse_hooks_block(
        {
            "DirectoryAdded": [
                {
                    "matcher": matcher,
                    "hooks": [{"type": "command", "command": f"{sys.executable} {script}"}],
                }
            ]
        },
        source="kullanici",
        path=Path("settings.json"),
    )
    assert not skipped
    return HookSession(root=tmp_path, loader=lambda: HookSet(commands)), log


async def _drain(session: HookSession) -> None:
    while session._background:
        await asyncio.gather(*list(session._background))


def test_olay_artik_tetikleniyor():
    assert "DirectoryAdded" not in CLAUDE_ONLY_EVENTS


def test_kanca_arka_planda_calisir_mesaj_sonraki_tura(tmp_path):
    session, log = _session(tmp_path)
    other = tmp_path / "diger"
    other.mkdir()

    async def run() -> None:
        directory_added(session, other)
        await _drain(session)

    asyncio.run(run())
    payload = json.loads(log.read_text())
    assert payload["hook_event_name"] == "DirectoryAdded"
    assert payload["directory"] == str(other)
    assert payload["source"] == "slash_command"
    assert session.take_rewake_notes() == ("DirectoryAdded hook: bağımlılıklar kuruldu",)


def test_add_dir_komutu_tetikler_ic_klasor_tetiklemez(tmp_path):
    root = tmp_path / "proje"
    (root / "alt").mkdir(parents=True)
    other = tmp_path / "diger"
    other.mkdir()
    session, log = _session(tmp_path)
    state = ReplState(config=make_config(), memory=null_memory(), root=root, home=tmp_path / "ev")
    state.hook_session = session

    async def run() -> None:
        add_dir(state, str(root / "alt"))  # kökün içinde: eklenmez, tetiklenmez
        await _drain(session)
        assert not log.exists()
        add_dir(state, str(other))
        await _drain(session)

    asyncio.run(run())
    assert json.loads(log.read_text())["directory"] == str(other.resolve())


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
    await _drain(state.hook_session)

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
    await _drain(state.hook_session)

    assert _satirlar(kayit) == []


async def test_baska_kaynak_eslestiricisi_tetiklenmez(tmp_path: Path, ev: Path) -> None:
    kok, ek = tmp_path / "proje", tmp_path / "diger"
    kok.mkdir()
    ek.mkdir()
    kayit = tmp_path / "kayit.jsonl"
    state = _durum(kok, ev, _kanca(tmp_path, kayit, "register_repo_root"))

    build_registry().get("add-dir").handler(state, str(ek))  # type: ignore[union-attr]
    await _drain(state.hook_session)

    assert _satirlar(kayit) == []


async def test_kanca_additionalcontext_sonraki_tura_baglam_olur(tmp_path: Path, ev: Path) -> None:
    """Kanca `additionalContext`'i kullanıcıya basılmaz, sonraki turda modele gider (#90, #213)."""
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
    await _drain(state.hook_session)

    # Claude: ekleme kancayı beklemez; mesaj ve bağlam kullanıcıya değil sonraki tura gider.
    notes = state.hook_session.take_rewake_notes()
    assert any("eklendi" in note for note in notes)
    assert any("yeni dizin notu" in note for note in notes)

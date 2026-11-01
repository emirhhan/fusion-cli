"""`DirectoryAdded` kancası (#90): `/add-dir` sonrası arka planda, systemMessage modele."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.workspace_commands import add_dir
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.hooks.events import CLAUDE_ONLY_EVENTS, HookSet
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

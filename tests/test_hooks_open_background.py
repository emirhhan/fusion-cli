"""Masaüstü açılışında arka planda SessionStart ve `reloadSkills` (#111)."""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
from pathlib import Path

import pytest

from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.engines.hooks.opening import open_soon, settle_opening
from fusion_cli.engines.hooks.session import HookSession

#: Kanca yükleme testleri güvenilmiş klasörde (#108; kapı: test_hooks_workspace_trust).
pytestmark = pytest.mark.usefixtures("guvenilir_klasor")


@pytest.fixture(autouse=True)
def _kancalar_acik(monkeypatch):
    monkeypatch.delenv("FUSION_HOOKS", raising=False)


def _start_hook(tmp_path: Path, output: dict[str, object]) -> HookCommand:
    log = tmp_path / "start.jsonl"
    script = tmp_path / "start.py"
    script.write_text(
        "import sys\n"
        f"open({str(log)!r}, 'a').write(sys.stdin.read().strip() + '\\n')\n"
        f"print({json.dumps(output)!r})\n",
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    return HookCommand(HookEvent.SESSION_START, "", command, 20.0, "kullanici", "")


def _runs(tmp_path: Path) -> int:
    log = tmp_path / "start.jsonl"
    return len(log.read_text().splitlines()) if log.exists() else 0


def test_acilista_arka_planda_calisir_ilk_tur_bekler_bir_kez(tmp_path):
    output = {
        "systemMessage": "hazır",
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "dal: ana"},
    }
    hooks = HookSet((_start_hook(tmp_path, output),))
    session = HookSession(root=tmp_path, loader=lambda: hooks)

    async def run() -> None:
        assert open_soon(session)
        assert not open_soon(session)  # ikinci çağrı yeni görev açmaz
        opened = await settle_opening(session)
        assert opened.system_messages == ("hazır",)
        assert (await session.start()).ran == 0
        assert (await settle_opening(session)).ran == 0

    asyncio.run(run())
    assert _runs(tmp_path) == 1
    assert "dal: ana" in session.take_start_context()


def test_sessionstart_tanimsizsa_baslatmaz(tmp_path):
    session = HookSession(root=tmp_path, loader=lambda: HookSet())

    async def run() -> None:
        assert not open_soon(session)

    asyncio.run(run())
    assert not session.started


def test_reload_skills_katalogu_tazeler(tmp_path):
    output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "reloadSkills": True}}
    hooks = HookSet((_start_hook(tmp_path, output),))
    calls: list[str] = []
    session = HookSession(root=tmp_path, loader=lambda: hooks)
    session.skills_reloader = lambda: calls.append("tazele")

    asyncio.run(session.start())

    assert calls == ["tazele"]


def test_repl_durumu_reload_skills_ile_katalogu_dusurur(tmp_path):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    state = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    session = state.hooks()
    assert session.skills_reloader is not None

    class _Registry:
        invalidated = False

        def invalidate(self) -> None:
            self.invalidated = True

    registry = _Registry()
    state.capabilities = registry  # type: ignore[assignment]
    session.skills_reloader()
    assert registry.invalidated


def test_masaustu_oturum_baslat_sessionstarti_beklemeden_baslatir(tmp_path, monkeypatch):
    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    home = tmp_path / "ev"
    monkeypatch.setenv("HOME", str(home))
    hook = _start_hook(tmp_path, {"systemMessage": "açıldı"})
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": hook.command}]}]}}
        ),
        encoding="utf-8",
    )
    root = tmp_path / "proje"
    root.mkdir()
    lines: list[str] = []

    async def run() -> None:
        app = AppSession(lines.append, root=root, home=home)
        await app.handle(Request(id="1", name="oturum.baslat", data={"sohbet_id": "sekme-1"}))
        session = app._state.hook_session
        assert session is not None and session.opening is not None
        opened = await settle_opening(session)
        assert opened.system_messages == ("açıldı",)

    asyncio.run(run())
    assert _runs(tmp_path) == 1

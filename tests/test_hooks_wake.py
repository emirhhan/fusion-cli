"""Boştaki oturumu uyandırma (#94 asyncRewake, #123 arka plan raporu): tur kendi başlar."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from fusion_cli.cli.repl import agent_link
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.hooks import parse_hooks_block
from fusion_cli.core.background_tasks import TaskStatus
from fusion_cli.core.hooks.events import HookEvent, HookSet
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools import agent_tasks
from fusion_cli.ui import background_messages as texts

from .fakes import make_config


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    value = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    yield value
    agent_link.close_link(value)


def _finish_task(state: ReplState) -> None:
    store = agent_tasks.task_store(state.config.memory_dir)
    task = store.create("iş", root=state.root, owner=state.conversation_id, name="isci")
    store.update(task.id, status=TaskStatus.COMPLETED, delivered=False, summary="bitti")
    store.write_result(task.id, "Sonuç hazır.")


def test_arka_plan_raporu_bostaki_oturumda_tur_baslatir(state):
    link = agent_link.open_link(state, kind="repl")
    _finish_task(state)

    busy = link.poll(state, busy=True)
    assert busy.turns == ()  # tur sürerken uyandırma beklemede
    idle = link.poll(state, busy=False)
    assert idle.turns == (texts.BG_WAKE_TURN,)
    assert link.poll(state, busy=False).turns == ()  # bir kez


def test_kullanici_raporu_tukettiyse_uyandirilmaz(state):
    link = agent_link.open_link(state, kind="repl")
    _finish_task(state)
    link.poll(state, busy=True)
    state.pending_blocks = []  # kullanıcının turu bağlamı aldı
    assert link.poll(state, busy=False).turns == ()


def _rewake_session(tmp_path: Path, exit_code: int) -> HookSession:
    script = tmp_path / "k.py"
    script.write_text(
        f"import sys\nsys.stderr.write('testler kırıldı')\nsys.exit({exit_code})\n",
        encoding="utf-8",
    )
    commands, skipped = parse_hooks_block(
        {
            "PostToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{sys.executable} {script}",
                            "asyncRewake": True,
                        }
                    ]
                }
            ]
        },
        source="kullanici",
        path=Path("settings.json"),
    )
    assert not skipped
    return HookSession(root=tmp_path, loader=lambda: HookSet(commands))


def _emit(session: HookSession) -> None:
    async def run() -> None:
        await session.emit(HookEvent.POST_TOOL_USE, subjects=("Bash",), fields={})
        while session._background:
            await asyncio.gather(*list(session._background))

    asyncio.run(run())


@pytest.mark.parametrize(("exit_code", "wakes"), [(2, True), (0, False)])
def test_async_rewake_cikis_2_bostaki_oturumu_uyandirir(state, tmp_path, exit_code, wakes):
    session = _rewake_session(tmp_path, exit_code)
    state.hook_session = session
    link = agent_link.open_link(state, kind="tui")

    _emit(session)

    assert session.wake_requested is wakes
    turns = link.poll(state, busy=False).turns
    assert turns == ((texts.HOOK_WAKE_TURN,) if wakes else ())
    if wakes:
        assert session.rewake_notes  # metin uyanan turun bağlamına gider


async def test_masaustu_uyandirma_turu_vadesi_gelenlerle_verilir(tmp_path, monkeypatch):
    import json

    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    monkeypatch.setenv("FUSION_KEYCHAIN", "off")
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")
    hooks = oturum._state.hooks()
    hooks.rewake_notes.append("PostToolUse hook (async): testler kırıldı")
    hooks.wake_requested = True

    async def rpc(kimlik: str) -> dict:
        await oturum.handle(Request(id=kimlik, name="cron.vadesi_gelenler", data={}))
        for satir in reversed(satirlar):
            paket = json.loads(satir)
            if paket.get("tip") == "sonuc" and paket.get("id") == kimlik:
                return paket["veri"]
        raise AssertionError(kimlik)

    first = await rpc("1")
    assert first["gorevler"] == [{"id": "", "gorev": texts.HOOK_WAKE_TURN, "kaynak": "ajan"}]
    assert (await rpc("2"))["gorevler"] == []

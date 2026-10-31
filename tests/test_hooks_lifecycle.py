"""Kanca yaşam döngüsü kalanları (P-009): `/reset` kimliği, SessionStart compact,
Notification idle_prompt, döküm araç çağrıları."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.hooks.events import HookCommand, HookEvent, HookSet
from fusion_cli.engines.hooks.session import HookSession
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture(autouse=True)
def _kancalar_acik(monkeypatch):
    monkeypatch.delenv("FUSION_HOOKS", raising=False)


def _kayit_kancasi(tmp_path: Path, event: HookEvent, matcher: str = "", cikti: str = ""):
    kayit = tmp_path / f"{event.value}.jsonl"
    script = tmp_path / f"kanca_{event.value}.py"
    script.write_text(
        "import sys\n"
        f"open({str(kayit)!r}, 'a', encoding='utf-8').write(sys.stdin.read().strip() + '\\n')\n"
        + (f"print({cikti!r})\n" if cikti else ""),
        encoding="utf-8",
    )
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"
    return HookCommand(event, matcher, command, 20.0, "test", "")


def _yukler(tmp_path: Path, event: HookEvent) -> list[dict]:
    path = tmp_path / f"{event.value}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _oturum(tmp_path: Path, *commands: HookCommand) -> HookSession:
    return HookSession(root=tmp_path, loader=lambda: HookSet(tuple(commands)))


# --- /reset sonrası yeni session_id ----------------------------------------------- #


async def test_reset_yeni_oturum_kimligi_verir_sohbet_kimligi_korunur(tmp_path):
    state = ReplState(
        config=make_config(),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path,
        conversation_id="sohbet",
    )
    state.hook_session = _oturum(
        tmp_path,
        _kayit_kancasi(tmp_path, HookEvent.SESSION_START),
        _kayit_kancasi(tmp_path, HookEvent.SESSION_END),
    )
    state.hook_session.conversation_id = "sohbet"
    state.hook_session.session_id = "sohbet"
    await state.hooks().start()

    state.reset_history()
    yeni = state.hooks()
    await yeni.start()
    await state.hooks().start()

    baslangiclar = _yukler(tmp_path, HookEvent.SESSION_START)
    bitis = _yukler(tmp_path, HookEvent.SESSION_END)
    assert (baslangiclar[0]["source"], baslangiclar[0]["session_id"]) == ("startup", "sohbet")
    assert baslangiclar[1]["source"] == "clear" and baslangiclar[1]["session_id"] != "sohbet"
    assert (bitis[0]["reason"], bitis[0]["session_id"]) == ("clear", "sohbet")
    # Sohbet aynı: sonraki tur oturumu yeniden başlatmaz, kimlik sabit kalır.
    assert len(baslangiclar) == 2 and state.conversation_id == "sohbet"
    assert state.hooks().session_id == baslangiclar[1]["session_id"]


# --- SessionStart(compact) -------------------------------------------------------- #


async def test_elle_compact_sessionstart_compact_tetikler_baglami_sonraki_tura_ekler(
    tmp_path, monkeypatch
):
    from fusion_cli.cli.repl import loop as repl_loop
    from fusion_cli.core.types import Message

    state = ReplState(config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path)
    state.history = [Message("user", f"soru {i}") for i in range(6)]
    state.hook_session = _oturum(
        tmp_path,
        _kayit_kancasi(tmp_path, HookEvent.SESSION_START, "compact", "kurallar: Türkçe yaz"),
    )

    async def _ozet(history, **kwargs):
        return history[:2]

    monkeypatch.setattr(repl_loop, "compress", _ozet)
    metin = await repl_loop.compact_history(state)

    assert "6" in metin and "2" in metin
    yuk = _yukler(tmp_path, HookEvent.SESSION_START)[0]
    assert yuk["source"] == "compact"
    assert any("kurallar: Türkçe yaz" in blok for blok in state.pending_blocks)
    # Oturum yaşam döngüsü değişmez: sonraki ilk tur yine SessionStart(startup) alır.
    assert state.hook_session.started is False


async def test_tur_ici_ozetleme_sessionstart_compact_baglamini_sisteme_ekler(tmp_path, monkeypatch):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent import compaction
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.engines.agent.approval import ApprovalMode, build_policy

    from .fakes import AlwaysApprove, RecordingSink
    from .test_hooks_loop import _Publisher

    session = _oturum(
        tmp_path,
        _kayit_kancasi(tmp_path, HookEvent.SESSION_START, "compact", "proje notu"),
        _kayit_kancasi(tmp_path, HookEvent.PRE_COMPACT),
    )
    deps = agent_loop.AgentDeps(
        config=make_config(),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        hooks=session,
    )
    uzun = [Message("system", "sistem"), *(Message("user", "x" * 4000) for _ in range(3))]
    kisa = [Message("system", "sistem"), Message("user", "özet")]

    async def _ozetle(messages, **kwargs):
        return kisa

    sorular = iter([True, False])
    monkeypatch.setattr(compaction, "compact_in_turn", _ozetle)
    monkeypatch.setattr(agent_loop, "needs_compression", lambda *a, **k: next(sorular, False))

    assert await agent_loop._compact_before_call(uzun, deps, agent_loop._State()) is True

    assert uzun[0].role == "system" and "proje notu" in uzun[0].content
    assert [m.content for m in uzun[1:]] == ["özet"]
    assert _yukler(tmp_path, HookEvent.PRE_COMPACT)[0]["trigger"] == "auto"
    assert _yukler(tmp_path, HookEvent.SESSION_START)[0]["source"] == "compact"

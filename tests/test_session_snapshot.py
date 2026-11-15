"""Sürdürülen oturumun tam durumu ve kalıcı checkpoint'ler (#187, #189).

Claude Code: sürdürmede araç çağrıları/sonuçları, compaction durumu, model ve izin kipi
geri gelir; checkpoint'ler konuşmayla saklanır, sürdürmeden sonra da `/rewind` çalışır.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from fusion_cli.cli.repl import session_resume, session_snapshot
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.core.turn_checkpoints import RewindScope
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path: Path, conversation_id: str = "session-abc") -> ReplState:
    config = make_config(memory_dir=tmp_path / "bellek")
    root = tmp_path / "proje"
    root.mkdir(exist_ok=True)
    state = ReplState(config=config, memory=null_memory(), root=root, home=tmp_path / "ev")
    state.conversation_id = conversation_id
    return state


def _tool_turn() -> list[Message]:
    call = ToolCall(id="c1", name="read_file", arguments='{"path": "a.txt"}')
    return [
        Message("user", "a.txt dosyasını oku"),
        Message("assistant", "", tool_calls=(call,)),
        Message("tool", "eski", tool_call_id="c1", name="read_file", ok=True),
        Message("assistant", "okudum"),
    ]


def _record_transcript(state: ReplState) -> None:
    store = TranscriptStore(state.config.memory_dir, state.root, conversation_id="session-abc")
    store.record_user("a.txt dosyasını oku")
    store.record_assistant("okudum")


def test_surdurmede_arac_cagrilari_model_ve_izin_kipi_geri_gelir(tmp_path):
    state = _state(tmp_path)
    _record_transcript(state)
    state.history = _tool_turn()
    state.approval = ApprovalMode.PLAN
    saved_mode = state.approval
    session_snapshot.save(state)
    path = session_snapshot.store_path(state.config.memory_dir, "session-abc")
    assert oct(path.stat().st_mode & 0o777) == "0o600"

    yeni = _state(tmp_path, conversation_id="session-baska")
    target = session_resume.resolve_launch(yeni.config.memory_dir, yeni.root, resume="session-abc")
    assert target is not None
    session_resume.apply_target(yeni, target)
    assert [message.role for message in yeni.history] == ["user", "assistant", "tool", "assistant"]
    assert yeni.history[1].tool_calls[0].name == "read_file"
    assert yeni.history[2].tool_call_id == "c1"
    assert yeni.approval is saved_mode


def test_bypass_kipi_surdurmede_geri_yuklenmez(tmp_path):
    state = _state(tmp_path)
    _record_transcript(state)
    state.history = _tool_turn()
    state.approval = ApprovalMode.BYPASS
    session_snapshot.save(state)
    yeni = _state(tmp_path, conversation_id="session-abc")
    yeni.approval = ApprovalMode.AUTO
    assert session_snapshot.restore(yeni) is True
    assert yeni.approval is ApprovalMode.AUTO


def test_transcript_daha_yeniyse_metin_gecmisi_korunur(tmp_path):
    state = _state(tmp_path)
    state.history = _tool_turn()
    session_snapshot.save(state, now=time.time() - 60)
    _record_transcript(state)  # sohbet başka yüzeyde sürdü
    yeni = _state(tmp_path)
    assert session_snapshot.restore(yeni) is False


def test_checkpoint_diskten_geri_kurulur_ve_rewind_dosyayi_geri_alir(tmp_path):
    state = _state(tmp_path)
    hedef = state.root / "a.txt"
    hedef.write_text("eski", encoding="utf-8")
    checkpoint = state.checkpoints.begin("a.txt'yi değiştir", [])
    checkpoint.changes.record(hedef)
    hedef.write_text("yeni", encoding="utf-8")
    checkpoint.changes.record_applied(hedef)
    state.history = [Message("user", "a.txt'yi değiştir"), Message("assistant", "tamam")]
    session_snapshot.save(state)

    yeni = _state(tmp_path)
    assert session_snapshot.restore(yeni) is True
    entries = yeni.checkpoints.entries()
    assert [entry.index for entry in entries] == [1]
    assert yeni.checkpoints.begin("sonraki", []).index == 2
    result = yeni.checkpoints.rewind(1, RewindScope.CODE)
    assert hedef in result.restored
    assert hedef.read_text(encoding="utf-8") == "eski"


def test_cleanup_period_days_eski_kayitlari_siler(tmp_path):
    ev = tmp_path / "ev"
    (ev / ".claude").mkdir(parents=True)
    (ev / ".claude" / "settings.json").write_text(json.dumps({"cleanupPeriodDays": 2}))
    assert session_snapshot.cleanup_period_days(ev) == 2
    bellek = tmp_path / "bellek"
    eski = session_snapshot.store_path(bellek, "session-eski")
    eski.parent.mkdir(parents=True)
    eski.write_text("{}")
    gun = 86_400
    os.utime(eski, (time.time() - 3 * gun, time.time() - 3 * gun))
    taze = session_snapshot.store_path(bellek, "session-taze")
    taze.write_text("{}")
    assert session_snapshot.prune(bellek, home=ev) == 1
    assert not eski.exists() and taze.exists()


@pytest.mark.parametrize("raw", ["bozuk", "{}", json.dumps({"surum": 1, "sohbet": "x"})])
def test_bozuk_kayit_yok_sayilir(tmp_path, raw):
    path = session_snapshot.store_path(tmp_path, "session-abc")
    path.parent.mkdir(parents=True)
    path.write_text(raw)
    assert session_snapshot.load(tmp_path, "session-abc") is None


def test_kayit_boyutu_tur_sayisiyla_karesel_buyumez(tmp_path):
    """Ölçüldü (1 Kasım): 100 checkpoint × tam geçmiş kopyası tek kayıtta 29,8 MB'tı (#187)."""
    state = _state(tmp_path)
    for tur in range(100):
        state.checkpoints.begin(f"tur{tur}", state.history)
        state.history.extend(
            [
                Message("user", f"istek {tur}"),
                Message("tool", "x" * 4000, tool_call_id="c", name="read_file", ok=True),
                Message("assistant", "y" * 1500),
            ]
        )
    session_snapshot.save(state)
    path = session_snapshot.store_path(state.config.memory_dir, "session-abc")
    assert path.stat().st_size < 1_500_000
    yeni = _state(tmp_path)
    snapshot = session_snapshot.load(yeni.config.memory_dir, "session-abc")
    assert snapshot is not None
    assert snapshot.history == tuple(state.history)
    assert [c.history_before for c in snapshot.checkpoints] == [
        c.history_before for c in state.checkpoints.entries()
    ]


def test_eski_surum_1_kaydi_okunur(tmp_path):
    from fusion_cli.memory.turn_journal_codec import message_to

    state = _state(tmp_path)
    path = session_snapshot.store_path(state.config.memory_dir, "session-abc")
    path.parent.mkdir(parents=True)
    eski = {
        "surum": 1,
        "sohbet": "session-abc",
        "zaman": time.time(),
        "gecmis": [message_to(Message("user", "merhaba"))],
        "model": "",
        "izin": "auto",
        "checkpointler": [
            {"no": 1, "gorev": "merhaba", "zaman": 1.0, "gecmis": [], "degisiklik": {}}
        ],
    }
    path.write_text(json.dumps(eski), encoding="utf-8")
    snapshot = session_snapshot.load(state.config.memory_dir, "session-abc")
    assert snapshot is not None
    assert snapshot.history[0].content == "merhaba"
    assert snapshot.checkpoints[0].task == "merhaba"

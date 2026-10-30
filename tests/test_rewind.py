"""`/rewind`: tur başına kod + konuşma checkpoint'i ve seçimli geri sarma (P-004).

Ölçüldü (31 Ekim): `/undo` yalnız son turu tutuyordu (`last_changes`); üç tur önceki
değişikliğe ya da konuşmanın eski bir noktasına dönmenin yolu yoktu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.appserver.commands import command_choices, run_command
from fusion_cli.cli.repl import rewind
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.transcript_store import TranscriptStore, load_transcript_messages
from fusion_cli.core.turn_checkpoints import (
    MAX_TURN_CHECKPOINTS,
    RewindScope,
    TurnCheckpointLedger,
    parse_scope,
)
from fusion_cli.core.types import Message
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _turn(ledger: TurnCheckpointLedger, task: str, history: list[Message], writes: dict[Path, str]):
    """Bir ajan turunu taklit et: checkpoint aç, dosyaları kaydedip yaz, geçmişi büyüt."""
    checkpoint = ledger.begin(task, history)
    for path, content in writes.items():
        checkpoint.changes.record(path)
        path.write_text(content, encoding="utf-8")
    history.extend([Message("user", task), Message("assistant", f"{task} yapıldı")])
    return checkpoint


# --- Çekirdek defter ------------------------------------------------------------------ #


def test_kod_ve_konusma_birlikte_geri_sarilir(tmp_path):
    ledger = TurnCheckpointLedger(clock=lambda: 1.0)
    dosya = tmp_path / "a.txt"
    dosya.write_text("v0", encoding="utf-8")
    history: list[Message] = []
    _turn(ledger, "bir", history, {dosya: "v1"})
    _turn(ledger, "iki", history, {dosya: "v2", tmp_path / "b.txt": "yeni"})
    _turn(ledger, "uc", history, {dosya: "v3"})

    result = ledger.rewind(2, RewindScope.BOTH)

    assert dosya.read_text(encoding="utf-8") == "v1", "2. turdan ÖNCEKİ hâl kazanır"
    assert not (tmp_path / "b.txt").exists()
    assert set(result.restored) == {dosya, tmp_path / "b.txt"}
    assert result.failed == ()
    assert [m.content for m in result.history or ()] == ["bir", "bir yapıldı"]
    assert result.keep_users == 1
    assert result.dropped_turns == 2
    assert [entry.index for entry in ledger.entries()] == [1]


def test_yalniz_kod_konusmayi_korur_kaydi_dusurur(tmp_path):
    ledger = TurnCheckpointLedger()
    dosya = tmp_path / "a.txt"
    history: list[Message] = []
    _turn(ledger, "bir", history, {dosya: "v1"})

    result = ledger.rewind(1, RewindScope.CODE)

    assert result.history is None
    assert not dosya.exists(), "turdan önce yoktu; geri alma siler"
    assert ledger.entries() == ()


def test_yalniz_konusma_dosyalara_dokunmaz_kod_kaydini_korur(tmp_path):
    ledger = TurnCheckpointLedger()
    dosya = tmp_path / "a.txt"
    history: list[Message] = []
    _turn(ledger, "bir", history, {dosya: "v1"})
    _turn(ledger, "iki", history, {dosya: "v2"})

    result = ledger.rewind(2, RewindScope.CONVERSATION)

    assert dosya.read_text(encoding="utf-8") == "v2"
    assert [m.content for m in result.history or ()] == ["bir", "bir yapıldı"]
    assert [entry.index for entry in ledger.entries()] == [1, 2], "kod kaydı kalır"
    assert ledger.find(2).history_before == result.history, "konuşma kopyası yeni geçmişe eşitlenir"
    sonra = ledger.rewind(2, RewindScope.CODE)
    assert dosya.read_text(encoding="utf-8") == "v1"
    assert sonra.restored == (dosya,)


def test_bilinmeyen_tur_hata_verir_ve_tavan_eskiyi_dusurur():
    ledger = TurnCheckpointLedger(limit=2)
    for ad in ("a", "b", "c"):
        ledger.begin(ad, [])
    assert [entry.index for entry in ledger.entries()] == [2, 3]
    with pytest.raises(ValueError):
        ledger.rewind(1, RewindScope.BOTH)
    assert MAX_TURN_CHECKPOINTS == 100


def test_kapsam_sozcukleri():
    assert parse_scope("konuşma") is RewindScope.CONVERSATION
    assert parse_scope("KOD") is RewindScope.CODE
    assert parse_scope("ikisi") is RewindScope.BOTH
    assert parse_scope("x") is None


# --- Slash komutu --------------------------------------------------------------------- #


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    root = tmp_path / "proje"
    root.mkdir()
    return ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=root,
        home=tmp_path / "ev",
    )


def _run(state: ReplState, line: str) -> str:
    name, argument = parse(line)
    command = build_registry().get(name)
    assert command is not None, line
    return command.handler(state, argument)


def _seed_turns(state: ReplState) -> Path:
    dosya = state.root / "a.txt"
    store = TranscriptStore(
        state.config.memory_dir, state.root, conversation_id=state.conversation_id
    )
    for ad in ("bir", "iki"):
        checkpoint = state.checkpoints.begin(ad, state.history)
        checkpoint.changes.record(dosya)
        dosya.write_text(ad, encoding="utf-8")
        state.history.extend([Message("user", ad), Message("assistant", f"{ad} yapıldı")])
        store.record_user(ad)
        store.record_assistant(f"{ad} yapıldı")
    return dosya


def test_rewind_argumanla_secici_acmadan_uygular_ve_transcripti_sarar(state):
    dosya = _seed_turns(state)

    sonuc = _run(state, "/rewind 2 ikisi")

    assert "1 dosya 2. turdan önceki hâline" in sonuc
    assert "Konuşma 2. turun başına sarıldı (2 mesaj kaldı)" in sonuc
    assert dosya.read_text(encoding="utf-8") == "bir"
    assert [m.content for m in state.history] == ["bir", "bir yapıldı"]
    yuklenen = load_transcript_messages(
        state.config.memory_dir, state.root, conversation_id=state.conversation_id
    )
    assert [m.content for m in yuklenen] == ["bir", "bir yapıldı"]
    assert state.last_changes is None


def test_rewind_sira_serbest_ve_hatali_arguman(state):
    _seed_turns(state)
    assert "Kullanım" in _run(state, "/rewind 1 2")
    assert "Kullanım" in _run(state, "/rewind yanlis")
    assert "Böyle bir tur yok: 9" in _run(state, "/rewind 9 kod")
    assert "Konuşma 2. turun" in _run(state, "/rewind konuşma 2")


def test_rewind_bos_defter_ve_checkpoint_takma_adi(state):
    assert _run(state, "/rewind") == "Geri sarılacak tur yok; henüz bir agent turu çalışmadı."
    assert build_registry().get("checkpoint") is build_registry().get("rewind")


def test_undo_defterden_son_turu_geri_alir(state):
    dosya = _seed_turns(state)

    sonuc = _run(state, "/undo")

    assert "2. turdan önceki hâline" in sonuc
    assert dosya.read_text(encoding="utf-8") == "bir"
    assert [entry.index for entry in state.checkpoints.entries()] == [1]
    assert len(state.history) == 4, "/undo konuşmaya dokunmaz"


def test_turn_choices_yeniden_eskiye_ve_dosya_sayisi(state):
    _seed_turns(state)
    secenekler = rewind.turn_choices(state.checkpoints.entries())
    assert [c.value for c in secenekler] == ["2", "1"]
    assert "1 dosya" in secenekler[0].description
    assert [c.value for c in rewind.scope_choices()] == ["ikisi", "konusma", "kod"]


# --- Masaüstü köprüsü ------------------------------------------------------------------ #


def test_masaustu_rewind_iki_adimli_secici_sonra_uygular(state):
    dosya = _seed_turns(state)
    registry = build_registry()

    assert command_choices(state, "rewind") is not None
    adim1 = run_command(registry, state, "rewind", "")
    assert adim1["ok"] and adim1["secici"]["adim"] == "tur"
    assert adim1["secici"]["devam"] == {"komut": "rewind", "arguman_on_eki": ""}
    adim2 = run_command(registry, state, "rewind", "2")
    assert adim2["secici"]["adim"] == "kapsam"
    assert adim2["secici"]["devam"]["arguman_on_eki"] == "2 "

    son = run_command(registry, state, "rewind", "2 kod")

    assert "secici" not in son and "2. turdan önceki" in son["metin"]
    assert dosya.read_text(encoding="utf-8") == "bir"


def test_masaustu_bos_defterde_secici_acmaz(state):
    assert command_choices(state, "rewind") is None
    assert run_command(build_registry(), state, "rewind", "")["metin"].startswith("Geri sarılacak")

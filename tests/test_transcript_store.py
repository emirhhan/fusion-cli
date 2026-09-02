from __future__ import annotations

import json

from fusion_cli.cli.repl.transcript_store import TranscriptStore, load_transcript_messages
from fusion_cli.core.events import EffectWorkflowFinished


def test_transcript_snapshot_ve_event_journal_kalici(tmp_path):
    store = TranscriptStore(tmp_path / "memory", tmp_path / "repo")
    store.save_snapshot("kullanıcı mesajı\nFusion cevabı")
    store.record_user("repoyu kontrol et")
    store.handle(
        EffectWorkflowFinished(
            workflow_id="wf-1",
            kind="git_push",
            status="completed",
            ok=True,
            title="Git push tamamlandı",
            details={"branch": "main", "local_head": "abc", "remote_head": "abc"},
            message="doğrulandı",
        )
    )

    reloaded = TranscriptStore(tmp_path / "memory", tmp_path / "repo")
    assert "Fusion cevabı" in reloaded.load_snapshot()
    lines = store.events_path.read_text(encoding="utf-8").splitlines()
    payloads = [json.loads(line) for line in lines]
    assert payloads[0]["event"] == "UserMessage"
    assert payloads[1]["event"] == "EffectWorkflowFinished"
    assert payloads[1]["details"]["branch"] == "main"


def test_sohbet_kimligi_verilince_yalniz_o_sohbetin_mesajlari_yuklenir(tmp_path):
    """Aynı proje kökünde iki sekme açıksa transcript'leri karışmamalı.

    Gerçek hata: depo yalnız proje köküne göre anahtarlanıyordu; kullanıcı bir
    sekmeye tıkladığında o sekmenin değil, projenin TÜM konuşması yükleniyordu.
    """
    memory = tmp_path / "memory"
    root = tmp_path / "repo"
    ilk = TranscriptStore(memory, root, conversation_id="sekme-a")
    ikinci = TranscriptStore(memory, root, conversation_id="sekme-b")

    ilk.record_user("oyun yaz")
    ilk.record_assistant("hazırlıyorum")
    ikinci.record_user("fatura tablosu")

    a = load_transcript_messages(memory, root, conversation_id="sekme-a")
    b = load_transcript_messages(memory, root, conversation_id="sekme-b")

    assert [m.content for m in a] == ["oyun yaz", "hazırlıyorum"]
    assert [m.content for m in b] == ["fatura tablosu"]


def test_kimliksiz_yukleme_proje_genelini_dondurur(tmp_path):
    """TUI kimlik vermez; eski davranış korunur."""
    memory = tmp_path / "memory"
    root = tmp_path / "repo"
    TranscriptStore(memory, root, conversation_id="sekme-a").record_user("bir")
    TranscriptStore(memory, root, conversation_id="sekme-b").record_user("iki")

    hepsi = load_transcript_messages(memory, root)

    assert [m.content for m in hepsi] == ["bir", "iki"]


def test_sohbet_kimligi_satirlara_yazilir(tmp_path):
    memory = tmp_path / "memory"
    root = tmp_path / "repo"
    store = TranscriptStore(memory, root, conversation_id="sekme-a")

    store.record_user("merhaba")

    satirlar = store.events_path.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(satirlar[0])["session_id"] == "sekme-a"

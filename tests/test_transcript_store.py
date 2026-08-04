from __future__ import annotations

import json

from fusion_cli.cli.repl.transcript_store import TranscriptStore
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

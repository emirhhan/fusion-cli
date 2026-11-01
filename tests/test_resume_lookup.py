"""`--resume` çözümü Claude Code kurallarıyla (#203)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl import resume_lookup, session_resume
from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.core.errors import SessionNotFoundError


def _sohbet(memory: Path, root: Path, conv: str, name: str = "") -> None:
    store = TranscriptStore(memory, root, conversation_id=conv)
    store.record_user(f"{conv} istemi")
    store.record_assistant(f"{conv} cevabı")
    if name:
        store.record_name(name)


def test_kimlik_baska_projede_tek_ise_bulunur(tmp_path: Path):
    memory, a, b = tmp_path / "m", tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    _sohbet(memory, b, "uzak-kimlik-123")
    found = resume_lookup.resolve(memory, a, "uzak-kimlik-123")
    assert found.ref is not None and found.events_path is not None
    target = session_resume.resolve_launch(memory, a, resume="uzak-kimlik-123")
    assert target is not None and any("uzak-kimlik-123 istemi" in m.content for m in target.history)
    c = tmp_path / "c"
    c.mkdir()
    _sohbet(memory, c, "uzak-kimlik-123")  # elle kopyalanmış eş
    assert resume_lookup.resolve(memory, a, "uzak-kimlik-123").ref is None


def test_ad_tam_eslesme_ve_belirsiz_ad(tmp_path: Path, monkeypatch):
    memory, root = tmp_path / "m", tmp_path / "p"
    root.mkdir()
    _sohbet(memory, root, "k1", name="Auth")
    assert resume_lookup.resolve(memory, root, "Auth").ref.conversation_id == "k1"
    _sohbet(memory, root, "k2", name="Auth")
    found = resume_lookup.resolve(memory, root, "Auth")
    assert found.ref is None and {r.conversation_id for r in found.ambiguous} == {"k1", "k2"}
    from fusion_cli.cli.repl import resume_launch

    monkeypatch.setattr(resume_launch, "_default_chooser", lambda choices, title: "k2")
    target = session_resume.resolve_launch(memory, root, resume="Auth")
    assert target is not None and target.conversation_id == "k2"
    monkeypatch.setattr(resume_launch, "_default_chooser", lambda choices, title: None)
    with pytest.raises(SessionNotFoundError):
        session_resume.resolve_launch(memory, root, resume="Auth")


def test_mutlak_jsonl_yolu_ile_surdurme(tmp_path: Path, monkeypatch):
    """Claude Code `--resume <transcript-path>` (#188): Fusion transcript dosyasının yolu."""
    from fusion_cli.cli.repl import resume_launch
    from fusion_cli.cli.repl.transcript_store import transcript_events_path

    memory, other, here = tmp_path / "m", tmp_path / "o", tmp_path / "h"
    other.mkdir(), here.mkdir()
    _sohbet(memory, other, "tek")
    path = transcript_events_path(memory, other)
    target = session_resume.resolve_launch(memory, here, resume=str(path))
    assert target is not None and target.conversation_id == "tek"
    _sohbet(memory, other, "ikinci")
    monkeypatch.setattr(resume_launch, "_default_chooser", lambda choices, title: "ikinci")
    target = session_resume.resolve_launch(memory, here, resume=str(path))
    assert target.conversation_id == "ikinci"
    assert any("ikinci istemi" in m.content for m in target.history)
    with pytest.raises(SessionNotFoundError):
        session_resume.resolve_launch(memory, here, resume=str(tmp_path / "yok.jsonl"))

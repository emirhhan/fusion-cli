"""Argümansız `--resume` / `-r` oturum seçicisini açar (#188)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.repl import resume_launch, session_resume
from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.core.errors import SessionNotFoundError

from .fakes import make_config


def test_degersiz_resume_secici_isareti_alir():
    picker = resume_launch.RESUME_PICKER
    assert resume_launch.normalize_resume_argv(["--resume"]) == ["--resume", picker]
    assert resume_launch.normalize_resume_argv(["-r", "--name", "x"]) == [
        "-r",
        picker,
        "--name",
        "x",
    ]
    assert resume_launch.normalize_resume_argv(["-r", "abc"]) == ["-r", "abc"]
    assert resume_launch.normalize_resume_argv(["run", "selam"]) == ["run", "selam"]


def test_secici_secilen_sohbeti_acar(tmp_path, monkeypatch):
    memory, root = tmp_path / "m", tmp_path / "r"
    store = TranscriptStore(memory, root, conversation_id="session-abc")
    store.record_user("oyun yaz")
    store.record_assistant("tamam")
    secenekler: list[str] = []

    def _sec(choices, _title):
        secenekler.extend(choice.value for choice in choices)
        return "session-abc"

    monkeypatch.setattr(resume_launch, "_default_chooser", _sec)

    target = session_resume.resolve_launch(memory, root, resume=resume_launch.RESUME_PICKER)

    assert secenekler == ["session-abc"]
    assert target is not None and target.conversation_id == "session-abc"
    assert len(target.history) == 2


def test_secici_vazgecilirse_oturum_acilmaz(tmp_path, monkeypatch):
    memory, root = tmp_path / "m", tmp_path / "r"
    TranscriptStore(memory, root, conversation_id="session-abc").record_user("selam")
    monkeypatch.setattr(resume_launch, "_default_chooser", lambda *_a: None)

    with pytest.raises(SessionNotFoundError):
        session_resume.resolve_launch(memory, root, resume=resume_launch.RESUME_PICKER)


def test_cli_argumansiz_resume_sohbet_yoksa_aciklayarak_cikar(tmp_path, monkeypatch):
    from fusion_cli.cli import app as app_module

    monkeypatch.setattr(app_module, "load_config", lambda: make_config(memory_dir=tmp_path / "m"))
    monkeypatch.setattr(app_module, "evaluate", lambda *_a, **_k: type("R", (), {"state": None})())
    monkeypatch.chdir(tmp_path)

    args = resume_launch.normalize_resume_argv(["--resume"])
    result = CliRunner().invoke(app_module.app, args)

    assert result.exit_code == 1
    assert "sürdürülecek Fusion sohbeti yok" in (result.stderr or "") + result.stdout

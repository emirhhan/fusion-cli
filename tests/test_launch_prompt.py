"""`fusion "query"`, `fusion -r <oturum> "query"` ve `--session-id <uuid>` (#204)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from fusion_cli.cli.repl.launch_prompt import (
    PROMPT_FLAG,
    ensure_unused,
    normalize_prompt_argv,
    session_id_value,
)
from fusion_cli.cli.repl.session_resume import resolve_launch
from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.core.errors import SessionNotFoundError

_SUBS = {"run", "agent", "doctor"}


def test_ilk_konum_argumani_istem_olur() -> None:
    assert normalize_prompt_argv(["sorum ne"], _SUBS) == [PROMPT_FLAG, "sorum ne"]


def test_resume_degeri_atlanir_sonraki_istem_olur() -> None:
    argv = ["-r", "oturum", "devam et"]
    assert normalize_prompt_argv(argv, _SUBS) == ["-r", "oturum", PROMPT_FLAG, "devam et"]


def test_alt_komut_dokunulmaz() -> None:
    assert normalize_prompt_argv(["-c", "agent", "görev"], _SUBS) == ["-c", "agent", "görev"]


def test_bayraksiz_ve_istemsiz_argv_ayni_kalir() -> None:
    assert normalize_prompt_argv(["--continue", "--name=x"], _SUBS) == ["--continue", "--name=x"]


def test_session_id_uuid_dogrulanir() -> None:
    value = uuid.uuid4()
    assert session_id_value(str(value)) == f"session-{value.hex}"
    with pytest.raises(SessionNotFoundError):
        session_id_value("uuid-degil")


def test_kullanilan_kimlik_reddedilir(tmp_path: Path) -> None:
    root = tmp_path / "proje"
    root.mkdir()
    kimlik = session_id_value(str(uuid.uuid4()))
    ensure_unused(tmp_path, root, kimlik)
    TranscriptStore(tmp_path, root, conversation_id=kimlik).record_user("merhaba")
    with pytest.raises(SessionNotFoundError):
        ensure_unused(tmp_path, root, kimlik)


def test_resolve_launch_session_id_yeni_sohbeti_o_kimlikle_acar(tmp_path: Path) -> None:
    root = tmp_path / "proje"
    root.mkdir()
    value = uuid.uuid4()

    target = resolve_launch(tmp_path, root, session_id=str(value))

    assert target is not None
    assert target.conversation_id == f"session-{value.hex}"
    assert target.history == ()


def test_cli_argumani_ilk_istemi_repl_e_verir(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from fusion_cli.cli import app as app_module

    alinan: dict[str, object] = {}

    async def sahte_repl(config, **kwargs):
        alinan.update(kwargs)
        return 0

    monkeypatch.setattr(app_module, "run_repl", sahte_repl)
    monkeypatch.setattr(app_module, "evaluate", lambda *a, **k: type("R", (), {"state": None})())
    monkeypatch.setattr(app_module, "open_memory", lambda *a, **k: None)
    monkeypatch.chdir(tmp_path)
    argv = normalize_prompt_argv(["merhaba dünya"], app_module.subcommand_names())

    sonuc = CliRunner().invoke(app_module.app, argv)

    assert sonuc.exit_code == 0, sonuc.output
    assert alinan["initial_prompt"] == "merhaba dünya"

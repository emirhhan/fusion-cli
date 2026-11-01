"""`fusion "query"`, `fusion -r <oturum> "query"` ve `--session-id <uuid>` (#204)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from fusion_cli.cli.print_argv import INITIAL_PROMPT_OPTION as PROMPT_FLAG
from fusion_cli.cli.repl.launch_prompt import ensure_unused, session_id_value
from fusion_cli.cli.repl.session_resume import resolve_launch
from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.core.errors import SessionNotFoundError


def normalize_prompt_argv(argv: list[str]) -> list[str]:
    """`fusion "query"` çevirisi tek uygulamadır: kök grup `rewrite_root_args` (#276)."""
    import typer

    from fusion_cli.cli import app as app_module
    from fusion_cli.cli.print_argv import rewrite_root_args

    return rewrite_root_args(argv, typer.main.get_command(app_module.app))


def test_ilk_konum_argumani_istem_olur() -> None:
    assert normalize_prompt_argv(["sorum ne"]) == [PROMPT_FLAG, "sorum ne"]


def test_resume_degeri_atlanir_sonraki_istem_olur() -> None:
    argv = ["-r", "oturum", "devam et"]
    assert normalize_prompt_argv(argv) == ["-r", "oturum", PROMPT_FLAG, "devam et"]


def test_alt_komut_dokunulmaz() -> None:
    assert normalize_prompt_argv(["agent", "görev"]) == ["agent", "görev"]


def test_bayraksiz_ve_istemsiz_argv_ayni_kalir() -> None:
    assert normalize_prompt_argv(["--continue", "--name=x"]) == ["--continue", "--name=x"]


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
    sonuc = CliRunner().invoke(app_module.app, ["merhaba dünya"])

    assert sonuc.exit_code == 0, sonuc.output
    assert alinan["initial_prompt"] == "merhaba dünya"


def test_from_pr_degeri_istem_sanilmaz() -> None:
    # Ölçüldü (1 Kasım): `fusion --from-pr 42` → "No such command 42" (#205).
    assert normalize_prompt_argv(["--from-pr", "42"]) == ["--from-pr", "42"]


def test_cli_from_pr_bosluklu_bicimle_seciciyi_acar(tmp_path: Path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from fusion_cli.cli import app as app_module
    from fusion_cli.cli.repl import pr_sessions

    istenen: list[str] = []

    async def sahte_repl(config, **kwargs):
        return 0

    def sahte_secici(memory_dir, root, value, chooser=None):
        istenen.append(value)
        raise SessionNotFoundError("eşleşme yok")

    monkeypatch.setattr(app_module, "run_repl", sahte_repl)
    monkeypatch.setattr(app_module, "evaluate", lambda *a, **k: type("R", (), {"state": None})())
    monkeypatch.setattr(app_module, "open_memory", lambda *a, **k: None)
    monkeypatch.setattr(pr_sessions, "pick_for_pr", sahte_secici)
    monkeypatch.chdir(tmp_path)
    sonuc = CliRunner().invoke(app_module.app, ["--from-pr", "42"])

    assert istenen == ["42"], sonuc.output
    assert sonuc.exit_code == 1

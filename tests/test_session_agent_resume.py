"""Oturum ajanı sürdürmede korunur; ajan artık yoksa uyarıyla varsayılana dönülür (#16)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.cli.repl import persona_commands, session_agent
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.memory.factory import null_memory
from tests.fakes import make_config


def _state(tmp_path: Path, conversation: str = "sohbet-1") -> ReplState:
    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=tmp_path,
        home=tmp_path / "ev",
    )
    state.conversation_id = conversation
    return state


def _agent(tmp_path: Path) -> Path:
    folder = tmp_path / ".claude" / "agents"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "denetci.md"
    path.write_text("---\nname: denetci\ndescription: inceler\n---\nİncele.", encoding="utf-8")
    return path


def test_secilen_ajan_sohbete_yazilir_ve_sohbet_degisince_geri_yuklenir(tmp_path: Path) -> None:
    _agent(tmp_path)
    first = _state(tmp_path)
    persona_commands.persona(first, "denetci")

    resumed = _state(tmp_path)
    note = session_agent.restore(resumed)

    assert note == ""
    assert resumed.persona is not None and resumed.persona.name == "denetci"


def test_kayitli_ajan_artik_yoksa_uyari_ve_varsayilan(tmp_path: Path) -> None:
    path = _agent(tmp_path)
    persona_commands.persona(_state(tmp_path), "denetci")
    path.unlink()

    resumed = _state(tmp_path)
    note = session_agent.restore(resumed)

    assert "denetci" in note and resumed.persona is None


def test_persona_kapatilinca_kayit_silinir(tmp_path: Path) -> None:
    _agent(tmp_path)
    state = _state(tmp_path)
    persona_commands.persona(state, "denetci")
    persona_commands.persona(state, "off")

    assert session_agent.load(state.config.memory_dir, "sohbet-1") == ""


def test_baslikta_ajan_adi_at_isaretiyle_gorunur(tmp_path: Path) -> None:
    from fusion_cli.cli.repl.loop import session_info
    from fusion_cli.ui.banner import _facts_line

    _agent(tmp_path)
    state = _state(tmp_path)
    persona_commands.persona(state, "denetci")

    assert "@denetci" in _facts_line(session_info(state)).plain

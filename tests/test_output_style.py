"""Çıktı stilleri (P-068): keşif, sistem istemine ekleme, /output-style komutu."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.appserver.commands import command_choices
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.output_style_command import output_style_command, style_choices
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.engines.agent.loop import _initial_messages
from fusion_cli.engines.agent.output_style import (
    DEFAULT_STYLE,
    discover_styles,
    find_style,
    style_prompt,
)
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _with_style(config, name: str):
    return replace(config, runtime=replace(config.runtime, output_style=name))


def test_yerlesik_stiller_kesfedilir():
    names = [style.name for style in discover_styles(None, None)]
    assert names[:4] == ["aciklayici", "ogretici", "ozlu", "varsayilan"] or set(names) >= {
        "varsayilan",
        "ozlu",
        "aciklayici",
        "ogretici",
    }
    assert find_style("ozlu", None, None).prompt.startswith("# Çıktı stili: Özlü")
    assert find_style(DEFAULT_STYLE, None, None).prompt == ""


def test_ozel_stil_kullanici_ve_proje_dizininden_okunur_proje_ezer(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    (home / ".claude" / "output-styles").mkdir(parents=True)
    (home / ".claude" / "output-styles" / "sirket.md").write_text(
        "---\nname: sirket\ndescription: Şirket sesi\nkeep-coding-instructions: false\n---\n"
        "Resmi yaz.",
        encoding="utf-8",
    )
    (root / ".fusion" / "cikti-stilleri").mkdir(parents=True)
    (root / ".fusion" / "cikti-stilleri" / "sirket.md").write_text(
        "---\nname: sirket\n---\nProje sesi.", encoding="utf-8"
    )
    style = find_style("sirket", home, root)
    assert style is not None and style.source == "proje" and style.prompt == "Proje sesi."
    kullanici = find_style("sirket", home, None)
    assert kullanici.description == "Şirket sesi" and kullanici.keep_coding_instructions is False


def test_stil_metni_varsayilanda_bos_secilide_dolu_bilinmeyende_bos(caplog):
    config = make_config()
    assert style_prompt(config, home=None, root=None) == ""
    assert "Özlü" in style_prompt(_with_style(config, "ozlu"), home=None, root=None)
    assert style_prompt(_with_style(config, "yok-boyle"), home=None, root=None) == ""
    assert "çıktı stili bulunamadı" in caplog.text


def test_stil_sistem_isteminin_sonuna_eklenir():
    messages = _initial_messages("görev", None, plan_mode=False, extra_system="Çıktı stili: Özlü")
    assert messages[0].role == "system" and messages[0].content.endswith("Çıktı stili: Özlü")


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def test_komut_listeler_secer_ve_kalicilastirir(state: ReplState, tmp_path: Path):
    assert build_registry().get("output-style") is not None
    liste = output_style_command(state, "")
    assert "etkin: varsayilan" in liste and "ozlu" in liste
    assert "Çıktı stili: ozlu" in output_style_command(state, "ozlu")
    assert state.config.runtime.output_style == "ozlu"
    assert "output_style: ozlu" in (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert load_config(tmp_path / "config.yaml").runtime.output_style == "ozlu"
    assert "Bilinmeyen çıktı stili" in output_style_command(state, "yok")
    assert any(choice.label.endswith("(etkin)") for choice in style_choices(state))


def test_masaustu_secici_ayni_listeyi_sunar(state: ReplState):
    payload = command_choices(state, "output-style", "")
    assert payload is not None and payload["tur"] == "secim"
    assert {row["deger"] for row in payload["secenekler"]} >= {"varsayilan", "ozlu"}
    assert payload["devam"]["komut"] == "output-style"

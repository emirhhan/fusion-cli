"""Görünüm (P-070): /theme paletleri, /tui görünümü, /search tam ekran araması."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.tui import FusionTui, format_status
from fusion_cli.cli.repl.view_commands import (
    apply_theme_setting,
    search_command,
    theme_choices,
    theme_command,
    tui_command,
)
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import banner, theme


@pytest.fixture(autouse=True)
def _koyuya_don():
    yield
    theme.apply_palette(theme.DEFAULT_THEME)


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def test_palet_uygulaninca_sabitler_ve_kip_renkleri_degisir():
    assert theme.CURRENT_THEME == "koyu" and theme.OK == "#3FB950"
    theme.apply_palette("daltonizm")
    assert theme.OK == "#1F77B4" and theme.MODE_COLORS["auto"] == "#1F77B4"
    assert theme.DIFF_ADD == theme.OK and theme.DIFF_ADD_BG == "#0B2238"
    assert "#1F77B4" in format_status("auto", "agent")
    with pytest.raises(ValueError, match="Bilinmeyen tema"):
        theme.apply_palette("mor")


def test_ansi_paletinde_gradyan_cokmez():
    theme.apply_palette("ansi")
    assert theme.blend(theme.ACCENT, theme.ACCENT_ALT, 0.5) == "yellow"
    rendered = banner.gradient("FUSION")
    assert rendered.plain == "FUSION"


def test_theme_komutu_listeler_uygular_ve_yazar(state: ReplState, tmp_path: Path):
    assert build_registry().get("theme") is not None
    liste = theme_command(state, "")
    assert "etkin: koyu" in liste and "daltonizm" in liste
    assert "Tema: acik" in theme_command(state, "acik")
    assert theme.CURRENT_THEME == "acik" and state.config.runtime.terminal_theme == "acik"
    assert load_config(tmp_path / "config.yaml").runtime.terminal_theme == "acik"
    assert "Bilinmeyen tema" in theme_command(state, "mor")
    assert any(c.label.endswith("(etkin)") and c.value == "acik" for c in theme_choices(state))


def test_oturum_basinda_kayitli_tema_uygulanir_bozuksa_koyu(state: ReplState):
    from dataclasses import replace

    state.config = replace(
        state.config, runtime=replace(state.config.runtime, terminal_theme="ansi")
    )
    apply_theme_setting(state)
    assert theme.CURRENT_THEME == "ansi"
    state.config = replace(
        state.config, runtime=replace(state.config.runtime, terminal_theme="yok")
    )
    apply_theme_setting(state)
    assert theme.CURRENT_THEME == "koyu"


def test_tui_komutu_gorunumu_kaydeder(state: ReplState, tmp_path: Path):
    assert "fullscreen" in tui_command(state, "")
    assert "inline olarak kaydedildi" in tui_command(state, "inline")
    assert load_config(tmp_path / "config.yaml").runtime.tui == "inline"
    assert "Bilinmeyen görünüm" in tui_command(state, "yarim")


def test_search_satir_icinde_yonlendirir_tam_ekranda_kaydirir(state: ReplState, monkeypatch):
    assert "Kullanım" in search_command(state, "")
    assert "yalnız tam ekran" in search_command(state, "x")
    monkeypatch.setattr("fusion_cli.cli.repl.tui._term_rows", lambda: 20)
    tui = FusionTui(
        on_submit=lambda _t: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )
    tui.console.print("\n".join(f"satır {i} {'HEDEF' if i in (5, 40) else ''}" for i in range(100)))
    tui.sync_conversation()
    assert tui.scroll_to_match("hedef") == 2
    assert tui._scroll == 100 - 40 - 1
    assert tui.scroll_to_match("yok-boyle") == 0


def test_refresh_style_tema_sonrasi_yeni_stil_kurar():
    tui = FusionTui(
        on_submit=lambda _t: None,
        on_interrupt=lambda: None,
        on_exit=lambda: None,
        on_cycle_mode=lambda: None,
    )
    before = tui.application.style
    theme.apply_palette("acik")
    tui.refresh_style()
    assert tui.application.style is not before

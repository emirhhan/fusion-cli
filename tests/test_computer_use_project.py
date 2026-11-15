"""Computer use varsayılan kapalı, proje başına `/mcp enable computer-use` (#420, #445)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.headless import apply_limits
from fusion_cli.cli.repl import commands
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config import computer_use_projects
from fusion_cli.config.loader import load_config
from fusion_cli.core.desktop_settings import DesktopSettings
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


@pytest.fixture
def store(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "ayar" / computer_use_projects.STORE_NAME
    monkeypatch.setattr(computer_use_projects, "store_path", lambda: path)
    return path


def test_varsayilan_kapali():
    assert DesktopSettings().enabled is False


def test_proje_kaydi_yalniz_o_projeyi_acar(tmp_path, store):
    proje, baska = tmp_path / "p", tmp_path / "q"
    proje.mkdir()
    baska.mkdir()
    computer_use_projects.set_enabled_for(proje, True)
    assert computer_use_projects.effective(DesktopSettings(), proje).enabled is True
    assert computer_use_projects.effective(DesktopSettings(), baska).enabled is False
    computer_use_projects.set_enabled_for(proje, False)
    assert computer_use_projects.effective(DesktopSettings(), proje).enabled is False


def test_bozuk_kayit_kapali_sayilir(tmp_path, store):
    store.parent.mkdir(parents=True)
    store.write_text("{bozuk", encoding="utf-8")
    assert computer_use_projects.is_enabled_for(tmp_path) is False


def test_load_config_proje_kaydini_okur(tmp_path, store, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 64\n", encoding="utf-8")
    assert load_config(source).desktop.enabled is False
    computer_use_projects.set_enabled_for(tmp_path, True)
    assert load_config(source).desktop.enabled is True


def test_etkilesimsiz_yol_her_zaman_kapali():
    config = make_config(desktop=DesktopSettings(enabled=True))
    limited = apply_limits(config, max_turns=None, max_budget_usd=None, bare=False)
    assert limited.desktop.enabled is False


def test_mcp_komutu_computer_use_satirini_gosterir_ve_acar(tmp_path, store):
    state = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    listing = commands._mcp(state, "")
    assert "computer-use" in listing and "disabled" in listing
    reply = commands._mcp(state, "enable computer-use")
    assert "açıldı" in reply and state.config.desktop.enabled is True
    assert computer_use_projects.is_enabled_for(tmp_path)
    assert "enabled (bu proje)" in commands._mcp(state, "list")
    commands._mcp(state, "disable computer-use")
    assert state.config.desktop.enabled is False
    assert not computer_use_projects.is_enabled_for(tmp_path)

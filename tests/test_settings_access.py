"""Nokta yoluyla ayar erişimi (P-029): /config, fusion config get/set/list, -c, --profile."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from fusion_cli.cli.app import app
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.config_command import config_command
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.config.settings_access import (
    apply_overrides,
    apply_setting,
    list_settings,
    parse_override,
    read_setting,
    write_setting,
)
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.reasoning import ReasoningEffort
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def test_listede_runtime_ve_embedding_var_ve_suzgec_calisir():
    rows = list_settings(make_config())
    paths = {row.path for row in rows}
    assert "runtime.max_tokens" in paths and "embedding.provider" in paths
    assert all(
        row.path.startswith("runtime.web") for row in list_settings(make_config(), "runtime.web")
    )
    kinds = {row.path: row.kind for row in rows}
    assert kinds["runtime.lessons"] == "boolean"
    assert "low" in kinds["runtime.reasoning_effort"]


def test_oku_ve_uygula_tipleri_dogrular():
    config = make_config()
    assert read_setting(config, "runtime.lessons") in ("true", "false")
    updated = apply_setting(config, "runtime.max_tokens", "4321")
    assert updated.runtime.max_tokens == 4321 and config.runtime.max_tokens != 4321
    assert apply_setting(config, "runtime.lessons", "kapalı").runtime.lessons is False
    assert (
        apply_setting(config, "runtime.reasoning_effort", "HIGH").runtime.reasoning_effort
        is ReasoningEffort.HIGH
    )
    assert apply_setting(config, "runtime.disabled_tools", "a, b").runtime.disabled_tools == (
        "a",
        "b",
    )
    assert apply_setting(config, "runtime.agent_max_steps", "null").runtime.agent_max_steps is None
    with pytest.raises(ConfigError, match="tam sayı"):
        apply_setting(config, "runtime.max_tokens", "çok")
    with pytest.raises(ConfigError, match="Bilinmeyen ayar"):
        apply_setting(config, "runtime.yok_boyle", "1")
    with pytest.raises(ConfigError, match="Bilinmeyen ayar bölümü"):
        apply_setting(config, "agent.model", "x")
    with pytest.raises(ConfigError, match="İzin verilen"):
        apply_setting(config, "runtime.reasoning_effort", "ultra")


def test_gecersiz_kilma_ciftleri():
    assert parse_override("runtime.max_tokens=12") == ("runtime.max_tokens", "12")
    with pytest.raises(ConfigError):
        parse_override("runtime.max_tokens")
    assert apply_overrides(make_config(), ("runtime.max_tokens=12",)).runtime.max_tokens == 12


def test_yazim_dosyaya_tek_anahtar_ekler_ve_geri_okunur(tmp_path: Path):
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n  lessons: false\n", encoding="utf-8")
    config = load_config(source)
    updated, target = write_setting(config, "runtime.max_tokens", "8192")
    assert target == source and updated.runtime.max_tokens == 8192
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    assert raw["runtime"] == {"max_tokens": 8192, "lessons": False}
    assert load_config(source).runtime.max_tokens == 8192
    write_setting(config, "runtime.agent_max_steps", "null")
    assert "agent_max_steps" not in yaml.safe_load(source.read_text(encoding="utf-8"))["runtime"]


def test_repl_config_komutu_listeler_okur_yazar(tmp_path: Path):
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    state = ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    registry = build_registry()
    assert registry.get("config") is not None
    liste = config_command(state, "")
    assert "runtime.max_tokens" in liste and "Ayarlar" in liste
    assert config_command(state, "runtime.max_tokens") == "runtime.max_tokens = 4096"
    sonuc = config_command(state, "runtime.max_tokens=2048")
    assert "runtime.max_tokens = 2048" in sonuc and str(source) in sonuc
    assert state.config.runtime.max_tokens == 2048
    assert "Bilinmeyen ayar" in config_command(state, "runtime.yok=1")
    name, argument = parse("/config runtime.max_tokens=1")
    assert name == "config" and argument == "runtime.max_tokens=1"


def test_cli_config_get_set_list(tmp_path: Path, monkeypatch):
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    monkeypatch.setenv("FUSION_CONFIG", str(source))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    assert runner.invoke(app, ["config", "get", "runtime.max_tokens"]).output.strip() == "4096"
    sonuc = runner.invoke(app, ["config", "set", "runtime.max_tokens", "777"])
    assert sonuc.exit_code == 0, sonuc.output
    assert yaml.safe_load(source.read_text(encoding="utf-8"))["runtime"]["max_tokens"] == 777
    liste = runner.invoke(app, ["config", "list", "runtime.max_tok"]).output
    assert "runtime.max_tokens = 777" in liste


def test_cli_c_alt_komutlarda_da_uygulanir_ve_dosyaya_yazmaz(tmp_path: Path, monkeypatch):
    """Ölçüldü (31 Ekim): `-c`/`--profile` yalnız argümansız `fusion`da uygulanıyor; alt komut
    varsa (`fusion -c … run`) callback erken dönüyor ve bayrak sessizce yok sayılıyordu."""
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    monkeypatch.setenv("FUSION_CONFIG", str(source))
    monkeypatch.setenv("HOME", str(tmp_path))
    runner = CliRunner()
    sonuc = runner.invoke(
        app, ["--set", "runtime.max_tokens=8192", "config", "get", "runtime.max_tokens"]
    )
    assert sonuc.exit_code == 0, sonuc.output
    assert "8192" in sonuc.output
    assert yaml.safe_load(source.read_text(encoding="utf-8"))["runtime"]["max_tokens"] == 4096
    hata = runner.invoke(app, ["--set", "runtime.yok=1", "config", "get", "runtime.max_tokens"])
    assert hata.exit_code == 2 and "4096" not in hata.output


def test_secimli_metin_alanlari_dogrulanir():
    """Ölçüldü (31 Ekim): `runtime.terminal_theme=mavi`, `runtime.tui=ful` 'tamam' deyip çalışma
    anında sessizce varsayılana düşüyordu."""
    from fusion_cli.cli.repl.view_commands import TUI_MODES
    from fusion_cli.config.settings_access import SETTING_CHOICES
    from fusion_cli.ui.theme import PALETTES

    with pytest.raises(ConfigError, match="İzin verilen"):
        apply_setting(make_config(), "runtime.terminal_theme", "mavi")
    with pytest.raises(ConfigError, match="İzin verilen"):
        apply_setting(make_config(), "runtime.tui", "ful")
    assert apply_setting(make_config(), "runtime.tui", "inline").runtime.tui == "inline"
    assert set(SETTING_CHOICES["runtime.terminal_theme"]) == set(PALETTES)
    assert tuple(SETTING_CHOICES["runtime.tui"]) == tuple(TUI_MODES)
    assert (
        "koyu|acik"
        in {row.path: row.kind for row in list_settings(make_config())}["runtime.terminal_theme"]
    )

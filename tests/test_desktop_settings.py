"""Bilgisayar kullanımı ayarları (P-006): `desktop:` bölümü, CLI yazımı, kayıt dışı bırakma, RPC."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from fusion_cli.appserver import computer_routes
from fusion_cli.cli.session import apply_runtime_settings
from fusion_cli.config.loader import load_config
from fusion_cli.config.settings_access import apply_setting, read_setting, write_setting
from fusion_cli.core.desktop_settings import DesktopLevel, DesktopSettings, parse_app_level
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.tools import ToolContext, ToolFamily, tool_family
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.engine_tools import build_agent_registry
from fusion_cli.engines.agent.loop import AgentDeps
from fusion_cli.engines.agent.team_scope import derive_sub_context

from .agent_harness import Publisher
from .fakes import AlwaysApprove, RecordingSink, make_config


async def _alt_ajan_yok(*args, **kwargs):
    raise AssertionError("alt ajan çalışmamalı")


def _registry(tmp_path: Path, desktop: DesktopSettings):
    deps = AgentDeps(
        config=make_config(desktop=desktop),
        publisher=Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )
    return build_agent_registry(deps, depth=0, run_agent=_alt_ajan_yok)


def _config_file(tmp_path: Path, text: str = "runtime:\n  max_tokens: 64\n") -> Path:
    source = tmp_path / "config.yaml"
    source.write_text(text, encoding="utf-8")
    return source


def _desktop_names(registry) -> set[str]:
    return {tool.name for tool in registry if tool_family(tool.name) is ToolFamily.DESKTOP}


def test_varsayilanlar_kod_ve_yaml_ile_ayni(tmp_path: Path):
    config = load_config(_config_file(tmp_path))

    assert config.desktop == DesktopSettings()


def test_eski_dosya_desktop_bolumu_olmadan_yuklenir(tmp_path: Path):
    assert load_config(_config_file(tmp_path)).desktop.enabled is True


def test_bozuk_app_levels_yuklemede_hata_verir(tmp_path: Path):
    source = _config_file(tmp_path, "desktop:\n  app_levels: ['Terminal=hepsi']\n")

    with pytest.raises(ConfigError, match=r"desktop\.app_levels"):
        load_config(source)


def test_app_level_ayristirici():
    assert parse_app_level(" Terminal = FULL ") == ("terminal", DesktopLevel.FULL)
    with pytest.raises(ValueError):
        parse_app_level("Terminal")


def test_config_set_desktop_enabled_dosyaya_yazar(tmp_path: Path):
    source = _config_file(tmp_path)
    config = load_config(source)

    updated, written = write_setting(config, "desktop.enabled", "false")

    assert written == source and updated.desktop.enabled is False
    assert yaml.safe_load(written.read_text())["desktop"] == {"enabled": False}
    assert load_config(source).desktop.enabled is False
    assert read_setting(updated, "desktop.control_level") == "full"


def test_config_set_kademe_ve_liste_dogrulanir(tmp_path: Path):
    config = load_config(_config_file(tmp_path))

    assert apply_setting(config, "desktop.control_level", "click").desktop.control_level is (
        DesktopLevel.CLICK
    )
    assert apply_setting(config, "desktop.denied_apps", "Mail, Notes").desktop.denied_apps == (
        "Mail",
        "Notes",
    )
    with pytest.raises(ConfigError):
        apply_setting(config, "desktop.control_level", "hepsi")
    with pytest.raises(ConfigError, match="uygulama=kademe"):
        apply_setting(config, "desktop.app_levels", "Terminal")


def test_kapaliyken_masaustu_ailesi_kayit_defterinde_yok(tmp_path: Path):
    acik = _registry(tmp_path, DesktopSettings())
    kapali = _registry(tmp_path, DesktopSettings(enabled=False))

    assert {"desktop_mouse", "desktop_screenshot", "desktop_key"} <= _desktop_names(acik)
    assert _desktop_names(kapali) == set()
    assert kapali.get("read_file") is not None


def test_ayar_tur_baglamina_ve_alt_ajana_gecer(tmp_path: Path):
    desktop = DesktopSettings(denied_apps=("Mail",), control_level=DesktopLevel.CLICK)
    context = apply_runtime_settings(ToolContext(root=tmp_path), make_config(desktop=desktop))

    assert context.desktop_settings == desktop
    assert derive_sub_context(context).desktop_settings == desktop


def test_rpc_ayarlar_ve_yazma(tmp_path: Path):
    source = _config_file(tmp_path)
    config = load_config(source)

    view, same = computer_routes.dispatch(config, "bilgisayar.ayarlar", {})
    assert view["ok"] is True and same is config
    assert view["ayarlar"]["control_level"] == "full"
    assert {item["deger"] for item in view["kademeler"]} == {"observe", "click", "full"}

    result, updated = computer_routes.dispatch(
        config, "bilgisayar.ayar_yaz", {"anahtar": "background", "deger": False}
    )
    assert result["ok"] is True and updated.desktop.background is False
    assert load_config(source).desktop.background is False

    bad, unchanged = computer_routes.dispatch(
        config, "bilgisayar.ayar_yaz", {"anahtar": "yok", "deger": True}
    )
    assert bad["ok"] is False and unchanged is config


def test_rpc_uygulama_reddet_tekrari_eklemez(tmp_path: Path):
    source = _config_file(tmp_path)
    config = load_config(source)

    first, config = computer_routes.dispatch(
        config, "bilgisayar.uygulama_reddet", {"uygulama": "Mail"}
    )
    again, config = computer_routes.dispatch(
        config, "bilgisayar.uygulama_reddet", {"uygulama": "mail"}
    )

    assert first["ok"] is True and again["ok"] is True
    assert config.desktop.denied_apps == ("Mail",)
    assert load_config(source).desktop.denied_apps == ("Mail",)

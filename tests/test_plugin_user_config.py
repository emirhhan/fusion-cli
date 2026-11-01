"""Eklenti `userConfig`, `plugin configure` ve `${user_config.KEY}` (Claude Code, #388)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store, plugin_user_config
from fusion_cli.core.plugins import PluginError
from fusion_cli.tools import plugin_install
from fusion_cli.tools.plugin_capabilities import with_plugin_root

runner = CliRunner()

_SCHEMA = {
    "api_url": {"type": "string", "title": "API", "description": "Adres", "required": True},
    "api_token": {"type": "string", "title": "Token", "description": "T", "sensitive": True},
    "limit": {"type": "number", "title": "Sınır", "description": "S", "min": 1, "max": 10},
    "tone": {
        "type": "string",
        "title": "Ton",
        "description": "T",
        "options": ["neutral", "warm"],
        "default": "neutral",
    },
}


def _install(tmp_path: Path) -> Path:
    folder = tmp_path / "kaynak"
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "rapor", "version": "1.0.0", "userConfig": _SCHEMA}), "utf-8"
    )
    skill = folder / "skills" / "ozet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Ö\n---\n"
        "U=${user_config.api_url} T=${user_config.api_token}\n",
        "utf-8",
    )
    plugin_install.install_plugin(str(folder), approve=lambda _p: True)
    return plugin_store.plugins_dir() / "rapor"


def test_sema_dogrulanir_bilinmeyen_alan_ve_tur_hata():
    with pytest.raises(PluginError, match="bilinmeyen alan"):
        plugin_user_config.parse_schema(
            {"a": {"type": "string", "title": "", "description": "", "x": 1}}
        )
    with pytest.raises(PluginError, match="geçersiz type"):
        plugin_user_config.parse_schema({"a": {"type": "renk", "title": "", "description": ""}})
    with pytest.raises(PluginError, match="geçersiz anahtar"):
        plugin_user_config.parse_schema({"1a": {"type": "string", "title": "", "description": ""}})


def test_configure_values_stdin_kaydeder_hassasi_ayri_0600_dosyada(tmp_path):
    _install(tmp_path)
    values = {"api_url": "https://x.example", "api_token": "gizli", "limit": "3"}
    result = runner.invoke(app, ["configure", "rapor", "--values-stdin"], input=json.dumps(values))
    assert result.exit_code == 0, result.output
    assert "Yapılandırma kaydedildi" in result.output
    base = plugin_store.plugins_dir()
    plain = json.loads((base / plugin_user_config.CONFIG_FILE).read_text("utf-8"))
    assert plain["pluginConfigs"]["rapor"]["options"] == {
        "api_url": "https://x.example",
        "limit": 3,
    }
    secret = base / plugin_user_config.SECRET_FILE
    assert "gizli" in secret.read_text("utf-8")
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600


def test_gecersiz_deger_hicbir_sey_kaydetmez_cikis_1(tmp_path):
    _install(tmp_path)
    values = {"api_url": "https://x.example", "limit": "99"}
    result = runner.invoke(app, ["configure", "rapor", "--values-stdin"], input=json.dumps(values))
    assert result.exit_code == 1
    assert "Yapılandırma kaydedilemedi" in result.output and "limit" in result.output
    assert not (plugin_store.plugins_dir() / plugin_user_config.CONFIG_FILE).exists()
    unknown = runner.invoke(app, ["configure", "rapor", "--values-stdin"], input='{"yok": "1"}')
    assert unknown.exit_code == 1


def test_configure_listesi_deger_basmaz_etiketler(tmp_path):
    _install(tmp_path)
    runner.invoke(app, ["configure", "rapor", "--values-stdin"], input='{"api_token": "gizli"}')
    result = runner.invoke(app, ["configure", "rapor"])
    assert result.exit_code == 0, result.output
    assert "api_url  required · not set" in result.output
    assert "api_token  optional · sensitive · set" in result.output
    assert "gizli" not in result.output
    missing = runner.invoke(app, ["configure", "yok@pazar"])
    assert missing.exit_code == 1


def test_beceri_govdesinde_hassas_olmayan_cozulur_hassas_yer_tutucu(tmp_path):
    root = _install(tmp_path)
    plugin_user_config.save_values(
        "rapor",
        plugin_user_config.read_schema(root),
        {"api_url": "https://x.example", "api_token": "gizli"},
        plugin_store.plugins_dir(),
    )
    path = root / "skills" / "ozet" / "SKILL.md"
    body = with_plugin_root(path.read_text("utf-8"), path)
    assert "U=https://x.example" in body
    assert "gizli" not in body and "[sensitive user_config.api_token]" in body


def test_kanca_ortami_ve_mcp_degiskeni():
    schema = plugin_user_config.parse_schema(_SCHEMA)
    values = {"api_url": "u", "api_token": "t", "tone": "warm"}
    env = dict(plugin_user_config.option_env(values))
    assert env["CLAUDE_PLUGIN_OPTION_API_TOKEN"] == "t"
    text = plugin_user_config.substitute("${user_config.api_token}", schema, values, content=False)
    assert text == "t"


def test_kanca_ortamina_ve_mcp_yapilandirmasina_degerler_iner(tmp_path):
    from fusion_cli.config.plugin_hooks import plugin_hooks

    folder = tmp_path / "kaynak"
    (folder / ".claude-plugin").mkdir(parents=True)
    manifest = {
        "name": "rapor",
        "userConfig": {"api_token": _SCHEMA["api_token"]},
        "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo x"}]}]},
        "mcpServers": {"api": {"command": "srv", "args": ["--token", "${user_config.api_token}"]}},
    }
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), "utf-8")
    plugin_install.install_plugin(str(folder), approve=lambda _p: True)
    root = plugin_store.plugins_dir() / "rapor"
    schema = plugin_user_config.read_schema(root)
    plugin_user_config.save_values("rapor", schema, {"api_token": "t"}, plugin_store.plugins_dir())

    commands, _skipped = plugin_hooks(default_timeout_s=5)
    assert ("CLAUDE_PLUGIN_OPTION_API_TOKEN", "t") in commands[0].env
    servers = plugin_store.plugin_mcp_servers()
    assert servers and "t" in servers[0].args

"""Eklentideki `.mcpb`/`.dxt` MCP paketleri ve `--config <sunucu>.<anahtar>` (#400)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from fusion_cli.config import plugin_store
from fusion_cli.config.plugin_layout import mcp_servers, validate_plugin
from fusion_cli.config.plugin_scan import scan_plugin
from fusion_cli.core.plugins import PluginError
from fusion_cli.tools import plugin_install
from fusion_cli.tools.plugin_install_config import apply_config


def _bundle(target: Path, *, required: bool) -> None:
    manifest = {
        "manifest_version": "0.2",
        "name": "veri-db",
        "version": "1.0.0",
        "server": {
            "type": "node",
            "entry_point": "server/index.js",
            "mcp_config": {
                "command": "node",
                "args": ["${__dirname}/server/index.js"],
                "env": {"API_KEY": "${user_config.api_key}"},
            },
        },
        "user_config": {
            "api_key": {
                "type": "string",
                "title": "API anahtarı",
                "description": "Servis anahtarı",
                "required": required,
                **({} if required else {"default": "varsayilan"}),
            }
        },
    }
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("server/index.js", "// sunucu\n")


def _plugin(tmp_path: Path, *, required: bool = False) -> Path:
    folder = tmp_path / "rapor"
    (folder / ".claude-plugin").mkdir(parents=True)
    manifest = {"name": "rapor", "mcpServers": "./sunucu.mcpb"}
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), "utf-8")
    _bundle(folder / "sunucu.mcpb", required=required)
    return folder


def test_mcpb_paketi_acilir_ve_claude_adiyla_sunucu_olur(tmp_path):
    layout = scan_plugin(_plugin(tmp_path))

    (server,) = mcp_servers(layout)

    assert server.name == "plugin:rapor:veri-db"
    assert server.command == "node"
    assert server.args[0].endswith("/server/index.js") and "${__dirname}" not in server.args[0]
    assert Path(server.args[0]).is_file()


def test_zorunlu_mcpb_degeri_yoksa_sunucu_atlanir_config_ile_baslar(tmp_path):
    source = _plugin(tmp_path, required=True)
    report = validate_plugin(source)
    assert report.servers == () and "needs configuration" in " ".join(report.warnings)
    item = plugin_install.install_plugin(str(source), approve=lambda _p: True)

    saved = apply_config(item.record, ["veri-db.api_key=gizli"], plugin_store.plugins_dir())

    assert saved == ("veri-db.api_key",)
    folder = plugin_store.plugin_folder(item.record)
    (server,) = mcp_servers(scan_plugin(folder))
    assert dict(server.env_literals)["API_KEY"] == "gizli"


def test_bilinmeyen_paket_sunucusu_config_hatasi(tmp_path):
    item = plugin_install.install_plugin(str(_plugin(tmp_path)), approve=lambda _p: True)

    with pytest.raises(PluginError, match=r"paketlenmiş \.mcpb sunucusu yok"):
        apply_config(item.record, ["yok.api_key=x"], plugin_store.plugins_dir())


def test_mcpb_adresi_manifestte_kabul_edilir(tmp_path, monkeypatch):
    from fusion_cli.config import plugin_mcpb

    bundle = tmp_path / "uzak.mcpb"
    _bundle(bundle, required=False)
    monkeypatch.setattr(plugin_mcpb, "_download", lambda ref, plugin: bundle)
    folder = tmp_path / "uzak"
    (folder / ".claude-plugin").mkdir(parents=True)
    manifest = {"name": "uzak", "mcpServers": ["https://ornek.example/s.mcpb"]}
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), "utf-8")

    (server,) = mcp_servers(scan_plugin(folder))

    assert server.name == "plugin:uzak:veri-db"

"""Eklenti açılınca ayarlanmamış userConfig seçenekleri sorulur (Claude /plugin, #388)."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.cli.repl import plugin_command
from fusion_cli.cli.repl.plugin_options_prompt import CONFIGURED, SKIPPED, prompt_after_enable
from fusion_cli.config import plugin_store
from fusion_cli.config import plugin_user_config as user_config
from fusion_cli.tools import plugin_install


def _plugin(tmp_path: Path) -> Path:
    folder = tmp_path / "rapor"
    (folder / ".claude-plugin").mkdir(parents=True)
    manifest = {
        "name": "rapor",
        "userConfig": {
            "bolge": {"type": "string", "title": "Bölge", "description": "Bölge"},
            "anahtar": {
                "type": "string",
                "title": "Anahtar",
                "description": "A",
                "sensitive": True,
            },
            "dil": {"type": "string", "title": "Dil", "description": "D", "default": "tr"},
        },
        "skills": "./",
    }
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), "utf-8")
    (folder / "SKILL.md").write_text("---\nname: rapor\ndescription: R\n---\nR\n", "utf-8")
    return folder


def test_ayarlanmamis_secenekler_sorulur_ve_kaydedilir(tmp_path):
    item = plugin_install.install_plugin(str(_plugin(tmp_path)), approve=lambda _p: True)
    asked: list[str] = []

    def ask(option):
        asked.append(option.key)
        return {"bolge": "eu", "anahtar": None}[option.key]

    text = prompt_after_enable(item.record, "rapor", ask=ask)

    assert asked == ["bolge", "anahtar"]  # varsayılanı olan `dil` sorulmaz
    assert text == CONFIGURED.format(name="rapor")
    assert user_config.saved_values("rapor", plugin_store.plugins_dir()) == {"bolge": "eu"}


def test_hepsi_bos_gecilirse_atlandi_ve_terminal_yoksa_ipucu(tmp_path):
    item = plugin_install.install_plugin(str(_plugin(tmp_path)), approve=lambda _p: True)

    assert prompt_after_enable(item.record, "rapor", ask=lambda _o: None) == SKIPPED
    hint = prompt_after_enable(item.record, "rapor")  # testte terminal yok
    assert "/plugin configure rapor" in hint


def test_repl_enable_ipucu_verir(tmp_path):
    item = plugin_install.install_plugin(str(_plugin(tmp_path)), approve=lambda _p: True)
    plugin_install.set_plugin_enabled(item.record.name, False)

    out = plugin_command._HANDLERS["enable"](None, ["rapor"], False, False)

    assert "/plugin configure rapor" in out


def test_tui_de_bekleyen_secenekler_uygulama_ici_istemle_sorulur(tmp_path, monkeypatch):
    import asyncio

    from fusion_cli.cli.repl import plugin_options_prompt as prompt

    item = plugin_install.install_plugin(str(_plugin(tmp_path)), approve=lambda _p: True)
    monkeypatch.setattr(prompt, "_tui_running", lambda: True)

    assert prompt_after_enable(item.record, "rapor") == ""  # TUI: istem komuttan sonra
    shown: list[str] = []
    kinds: list[str] = []

    async def text() -> str:
        kinds.append("metin")
        return "eu"

    async def secret() -> str:
        kinds.append("gizli")
        return "s3cr3t"

    results = asyncio.run(prompt.drain_tui(shown.append, text, secret))

    assert results == [CONFIGURED.format(name="rapor")]
    assert kinds == ["metin", "gizli"] and shown[0].startswith("Bölge (bolge")
    assert user_config.saved_values("rapor", plugin_store.plugins_dir())["bolge"] == "eu"
    assert asyncio.run(prompt.drain_tui(shown.append, text, secret)) == []

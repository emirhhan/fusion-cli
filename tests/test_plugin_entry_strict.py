"""Pazar girdisinin bildirim alanları ve strict modu (Claude Code marketplace-reference, #398)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config import plugin_store
from fusion_cli.core.plugin_marketplace import parse_marketplace
from fusion_cli.core.plugins import PluginError
from fusion_cli.tools import plugin_entry, plugin_install


def _folder(tmp_path: Path, *, manifest: dict[str, object] | None) -> Path:
    folder = tmp_path / "eklenti"
    (folder / "skills" / "ozet").mkdir(parents=True)
    (folder / "skills" / "ozet" / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
    )
    (folder / "ek").mkdir()
    (folder / "ek" / "yayinla.md").write_text("Yayınla\n", "utf-8")
    if manifest is not None:
        (folder / ".claude-plugin").mkdir()
        (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), "utf-8")
    return folder


def _manifest(folder: Path) -> dict[str, object]:
    return json.loads((folder / ".claude-plugin" / "plugin.json").read_text("utf-8"))


def test_girdi_alanlari_ve_strict_ayristirilir():
    market = parse_marketplace(
        {
            "name": "ekip",
            "owner": {"name": "E"},
            "plugins": [
                {"name": "a", "source": "./a", "commands": ["./ek"], "strict": False, "tags": []},
                {"name": "b", "source": "./b"},
            ],
        }
    )
    first, second = market.entries
    assert first.strict is False and json.loads(first.fields) == {"commands": ["./ek"]}
    assert second.strict is True and second.fields == ""


def test_bildirim_yoksa_girdi_bildirimdir(tmp_path):
    folder = _folder(tmp_path, manifest=None)

    plugin_entry.apply_entry(folder, '{"description": "Girdi", "version": "3.0.0"}', True, "rapor")

    assert _manifest(folder) == {"name": "rapor", "description": "Girdi", "version": "3.0.0"}


def test_strict_true_bilesenleri_ekler_kancalar_olay_basina_yer_degistirir(tmp_path):
    hooks = {"Stop": [{"hooks": [{"type": "command", "command": "eski"}]}]}
    folder = _folder(
        tmp_path, manifest={"name": "rapor", "commands": "./komutlar", "hooks": {"hooks": hooks}}
    )
    entry_hooks = {"Stop": [{"hooks": [{"type": "command", "command": "yeni"}]}]}
    fields = {"commands": ["./ek"], "hooks": entry_hooks, "defaultEnabled": False}

    plugin_entry.apply_entry(folder, json.dumps(fields), True, "rapor")

    data = _manifest(folder)
    assert data["commands"] == ["./komutlar", "./ek"]
    assert data["hooks"] == {"hooks": entry_hooks}
    assert data["defaultEnabled"] is False


def test_strict_false_bilesen_cakismasi_hata(tmp_path):
    folder = _folder(tmp_path, manifest={"name": "rapor"})

    with pytest.raises(PluginError, match="has conflicting manifests"):
        plugin_entry.apply_entry(folder, '{"commands": ["./ek"]}', False, "rapor")
    plugin_entry.apply_entry(folder, '{"description": "x"}', False, "rapor")  # bileşen yok: geçer


def test_girdide_dosya_yolu_kanca_desteklenmez(tmp_path):
    folder = _folder(tmp_path, manifest={"name": "rapor"})

    with pytest.raises(PluginError, match="not yet supported in a marketplace entry"):
        plugin_entry.apply_entry(folder, '{"hooks": "./hooks/ek.json"}', True, "rapor")


def test_git_kaynakli_girdinin_bilesenleri_kurulumda_uygulanir(tmp_path, monkeypatch):
    def fake_clone(url, target, *, ref="", sha=""):
        (target / "skills" / "ozet").mkdir(parents=True)
        (target / "skills" / "ozet" / "SKILL.md").write_text(
            "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
        )
        return "b" * 40

    monkeypatch.setattr(plugin_install, "_clone", fake_clone)
    market = tmp_path / "pazar"
    (market / ".claude-plugin").mkdir(parents=True)
    entry = {
        "name": "rapor",
        "source": {"source": "github", "repo": "ekip/rapor"},
        "description": "Girdiden",
        "version": "2.0.0",
    }
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "ekip", "owner": {"name": "E"}, "plugins": [entry]}), "utf-8"
    )
    plugin_install.add_marketplace(str(market))

    item = plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)

    assert item.record.version == "2.0.0"
    assert item.layout is not None and item.layout.manifest.description == "Girdiden"
    assert plugin_store.load_state().plugin("rapor") is not None


def _local_market(tmp_path: Path, entry: dict[str, object], manifest: dict[str, object]) -> Path:
    market = tmp_path / "pazar"
    plugin = _folder(market / "plugins", manifest=manifest)
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "ekip",
                "owner": {"name": "E"},
                "plugins": [{"name": "rapor", "source": "./plugins/eklenti", **entry}],
            }
        ),
        "utf-8",
    )
    plugin_install.add_marketplace(str(market))
    return plugin


def test_yerinde_yuklenen_eklentide_girdi_alanlari_uygulanir_kaynak_degismez(tmp_path):
    entry = {"commands": ["./ek"], "description": "Girdi", "defaultEnabled": False}
    plugin = _local_market(tmp_path, entry, {"name": "rapor", "description": "Bildirim"})
    before = (plugin / ".claude-plugin" / "plugin.json").read_text("utf-8")

    item = plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)

    assert item.record.folder == str(plugin.resolve())
    assert item.layout is not None
    assert item.layout.manifest.description == "Girdi"
    assert any(path.name == "yayinla.md" for _name, path in item.layout.commands)
    assert item.record.enabled is False  # girdinin defaultEnabled'ı
    assert (plugin / ".claude-plugin" / "plugin.json").read_text("utf-8") == before
    again = plugin_store.inspect_plugin(plugin_store.load_state().plugin("rapor"))
    assert again.layout is not None and again.layout.manifest.description == "Girdi"


def test_yerinde_strict_false_bilesen_cakismasi_kurulmaz(tmp_path):
    _local_market(tmp_path, {"commands": ["./ek"], "strict": False}, {"name": "rapor"})
    with pytest.raises(PluginError, match="conflicting manifests"):
        plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)


def test_yerinde_eklenti_guncellemesi_degisen_girdi_alanlarini_alir(tmp_path):
    from fusion_cli.tools import plugin_update

    _local_market(tmp_path, {"description": "Eski"}, {"name": "rapor"})
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    market_file = tmp_path / "pazar" / ".claude-plugin" / "marketplace.json"
    data = json.loads(market_file.read_text("utf-8"))
    data["plugins"][0]["description"] = "Yeni"
    market_file.write_text(json.dumps(data), "utf-8")

    result = plugin_update.update_plugin("rapor", approve=lambda _p: True)

    assert result.changed is True
    item = plugin_store.inspect_plugin(plugin_store.load_state().plugin("rapor"))
    assert item.layout is not None and item.layout.manifest.description == "Yeni"

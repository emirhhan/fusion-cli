"""Eklenti otomatik güncellemesi (Claude Code plugins/loading.md "When auto-update runs", #394).

Ağ YOK: pazarlar yerel klasördür; yerinde yüklenen eklentinin sürümü kaynakta değiştirilir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.config import plugin_store, trust
from fusion_cli.tools import plugin_auto_update, plugin_install

_ENVS = (
    "DISABLE_UPDATES",
    "DISABLE_AUTOUPDATER",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "FORCE_AUTOUPDATE_PLUGINS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENVS:
        monkeypatch.delenv(name, raising=False)


def _market(tmp_path: Path, name: str = "ekip") -> Path:
    market = tmp_path / name
    plugin = market / "plugins" / "rapor"
    (plugin / ".claude-plugin").mkdir(parents=True)
    _version(plugin, "1.0.0")
    (plugin / "skills" / "ozet").mkdir(parents=True)
    (plugin / "skills" / "ozet" / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
    )
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": name,
                "owner": {"name": "E"},
                "plugins": [{"name": "rapor", "source": "./plugins/rapor"}],
            }
        ),
        "utf-8",
    )
    plugin_install.add_marketplace(str(market))
    plugin_install.install_plugin(f"rapor@{name}", approve=lambda _p: True)
    return plugin


def _version(plugin: Path, version: str) -> None:
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "rapor", "version": version}), "utf-8"
    )


def _declare(project: Path, auto: bool | None) -> None:
    entry: dict[str, object] = {
        "source": {"source": "directory", "path": str(project.parent / "ekip")}
    }
    if auto is not None:
        entry["autoUpdate"] = auto
    path = project / ".claude" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"extraKnownMarketplaces": {"ekip": entry}}), "utf-8")
    trust.trust_project(project)


def test_ucuncu_taraf_pazar_varsayilan_kapali(tmp_path):
    plugin = _market(tmp_path)
    _version(plugin, "1.1.0")
    assert plugin_auto_update.auto_update_pass(tmp_path / "proje") == ()


def test_bildirimdeki_autoupdate_true_guncellenir_bildirim_metni(tmp_path):
    plugin = _market(tmp_path)
    project = tmp_path / "proje"
    _declare(project, True)
    _version(plugin, "1.1.0")
    assert plugin_auto_update.auto_update_pass(project) == ("rapor",)
    assert plugin_auto_update.NOTICE.format(name="rapor") == (
        "Plugin updated: rapor · Run /reload-plugins to apply"
    )
    assert plugin_auto_update.auto_update_pass(project) == ()  # zaten güncel


@pytest.mark.parametrize(
    "env", ["DISABLE_UPDATES", "DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"]
)
def test_ortam_degiskeni_kapatir_force_acar(tmp_path, monkeypatch, env):
    plugin = _market(tmp_path)
    project = tmp_path / "proje"
    _declare(project, True)
    _version(plugin, "1.1.0")
    monkeypatch.setenv(env, "1")
    assert plugin_auto_update.auto_update_pass(project) == ()
    monkeypatch.setenv("FORCE_AUTOUPDATE_PLUGINS", "1")
    assert plugin_auto_update.auto_update_pass(project) == ("rapor",)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("claude-plugins-official", True),
        ("knowledge-work-plugins", False),
        ("first-party-plugins", False),
        ("ekip", False),
    ],
)
def test_varsayilan_resmi_pazarlarda_acik(name, expected):
    assert plugin_auto_update.is_auto_update(name, {}) is expected


def test_bildirimdeki_false_resmi_varsayilani_ezer(tmp_path):
    from fusion_cli.tools.plugin_declared import DeclaredMarket

    declared = {
        "claude-plugins-official": DeclaredMarket("claude-plugins-official", "x", "project", False)
    }
    assert plugin_auto_update.is_auto_update("claude-plugins-official", declared) is False


def _official_clone(name: str):
    def fake_clone(url, target, *, ref="", sha=""):
        plugin = target / "plugins" / "rapor"
        (plugin / ".claude-plugin").mkdir(parents=True)
        _version(plugin, "1.0.0")
        (plugin / "skills" / "ozet").mkdir(parents=True)
        (plugin / "skills" / "ozet" / "SKILL.md").write_text(
            "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
        )
        (target / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        (target / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": name,
                    "owner": {"name": "Anthropic"},
                    "plugins": [{"name": "rapor", "source": "./plugins/rapor"}],
                }
            ),
            "utf-8",
        )
        return "b" * 40

    return fake_clone


def test_resmi_pazar_resmi_kaynaktan_eklenir_ve_varsayilan_acik(tmp_path, monkeypatch):
    """#411: ayrılmış ad yalnız github.com/anthropics/ kaynağına serbest; #394 DEFAULT_ON."""
    monkeypatch.setattr(plugin_install, "_clone", _official_clone("claude-plugins-official"))

    record = plugin_install.add_marketplace("resmi")

    assert record.name == "claude-plugins-official"
    assert plugin_auto_update.is_auto_update(record.name, {}) is True


def test_resmi_pazar_eklentisi_otomatik_guncellenir(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_install, "_clone", _official_clone("claude-plugins-official"))
    plugin_install.add_marketplace("resmi")
    plugin_install.install_plugin("rapor@claude-plugins-official", approve=lambda _p: True)

    def newer(url, target, *, ref="", sha=""):
        commit = _official_clone("claude-plugins-official")(url, target, ref=ref, sha=sha)
        _version(target / "plugins" / "rapor", "2.0.0")
        return commit

    monkeypatch.setattr(plugin_install, "_clone", newer)
    from fusion_cli.tools import plugin_update

    monkeypatch.setattr(plugin_update, "_clone", newer)
    assert plugin_auto_update.auto_update_pass(tmp_path / "proje") == ("rapor",)


def test_ayrilmis_ad_baska_kaynaktan_reddedilir(monkeypatch):
    from fusion_cli.core.plugins import PluginError

    monkeypatch.setattr(plugin_install, "_clone", _official_clone("claude-plugins-official"))
    with pytest.raises(PluginError, match="ayrılmış"):
        plugin_install.add_marketplace("saldirgan/claude-plugins-official")


def test_taklit_ad_resmi_kaynaktan_da_reddedilir(monkeypatch):
    from fusion_cli.core.plugins import PluginError

    monkeypatch.setattr(plugin_install, "_clone", _official_clone("official-claude-plugins"))
    with pytest.raises(PluginError, match="ayrılmış"):
        plugin_install.add_marketplace("resmi")


def test_resmi_pazar_ilk_etkilesimli_oturumda_bir_kez_eklenir(tmp_path, monkeypatch):
    """#394: claude-plugins-official ilk etkileşimli oturumda kendiliğinden eklenir."""
    for name in plugin_auto_update.DISABLE_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(plugin_install, "_clone", _official_clone("claude-plugins-official"))

    assert plugin_auto_update.ensure_official_marketplace() is True
    state = plugin_store.load_state()
    assert state.marketplace("claude-plugins-official") is not None
    plugin_install.remove_marketplace("claude-plugins-official")
    assert plugin_auto_update.ensure_official_marketplace() is False  # kaldırılırsa geri gelmez
    assert plugin_store.load_state().marketplace("claude-plugins-official") is None


def test_resmi_pazar_ag_kapaliysa_eklenmez_ve_bildirimler_kuyruktan_bosalir(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
    assert plugin_auto_update.ensure_official_marketplace() is False
    plugin_auto_update.push_notice("Plugin updated: a · Run /reload-plugins to apply")
    assert plugin_auto_update.drain_notices() == (
        "Plugin updated: a · Run /reload-plugins to apply",
    )
    assert plugin_auto_update.drain_notices() == ()


def test_resmi_kisa_adi_kullanimdan_kalkti_uyarisi(caplog):
    from fusion_cli.tools.plugin_market_source import parse_market_source

    assert parse_market_source("resmi").location.endswith("claude-plugins-official")
    assert "'resmi' kısa adı kullanımdan kalktı" in caplog.text

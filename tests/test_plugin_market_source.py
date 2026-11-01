"""marketplace add kaynak biçimleri (#395)."""

from __future__ import annotations

import json

import pytest

from fusion_cli.core.plugins import PluginError
from fusion_cli.tools import plugin_install
from fusion_cli.tools.plugin_market_source import (
    ERR_FORMAT,
    KIND_FILE,
    KIND_GIT,
    parse_market_source,
)


@pytest.mark.parametrize(
    ("spec", "location", "ref"),
    [
        ("sahip/depo", "https://github.com/sahip/depo", ""),
        ("sahip/depo#v1.2", "https://github.com/sahip/depo", "v1.2"),
        ("sahip/depo@main", "https://github.com/sahip/depo", "main"),
        ("https://git.ornek.com/x.git#dev", "https://git.ornek.com/x.git", "dev"),
        ("https://dev.azure.com/o/p/_git/r", "https://dev.azure.com/o/p/_git/r", ""),
        ("https://gitlab.com/grup/alt/proje", "https://gitlab.com/grup/alt/proje", ""),
        ("resmi", "https://github.com/anthropics/claude-plugins-official", ""),
    ],
)
def test_git_kaynaklari(spec, location, ref):
    source = parse_market_source(spec)
    assert (source.kind, source.location, source.ref) == (KIND_GIT, location, ref)


@pytest.mark.parametrize(
    ("spec", "part"),
    [
        ("git@github.com:o/r.git", "SSH"),
        ("http://ornek.com/x.git", "Yalnız https"),
        ("https://ornek.com/marketplace.json", "url türü"),
        ("gitlab.ornek.com/ekip/eklentiler", "başına https://"),
        ("tek", ERR_FORMAT),
        ("./yok", "bulunamadı"),
    ],
)
def test_reddedilen_kaynaklar(spec, part):
    with pytest.raises(PluginError, match=part.replace(".", r"\.").replace("?", r"\?")):
        parse_market_source(spec)


def test_json_dosyasi_pazari_yerinde_okunur_ve_goreli_eklenti_kurulur(tmp_path):
    plugin = tmp_path / "pazar" / "plugins" / "rapor"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "rapor"}', "utf-8")
    (plugin / "skills" / "ozet").mkdir(parents=True)
    (plugin / "skills" / "ozet" / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
    )
    file = tmp_path / "pazar" / ".claude-plugin" / "ekip.json"
    file.parent.mkdir()
    file.write_text(
        json.dumps(
            {
                "name": "ekip",
                "owner": {"name": "E"},
                "plugins": [{"name": "rapor", "source": "./plugins/rapor"}],
            }
        ),
        "utf-8",
    )
    assert parse_market_source(str(file)).kind == KIND_FILE

    record = plugin_install.add_marketplace(str(file))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)

    assert record.kind == KIND_FILE
    from fusion_cli.config import plugin_store

    assert plugin_store.load_state().plugin("rapor").folder == str(plugin.resolve())


def test_git_subdir_kaynagi_depodaki_alt_klasoru_kurar(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_clone(url, target, *, ref="", sha=""):
        calls.append(url)
        plugin = target / "araclar" / "rapor"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "rapor"}', "utf-8")
        (plugin / "skills" / "ozet").mkdir(parents=True)
        (plugin / "skills" / "ozet" / "SKILL.md").write_text(
            "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
        )
        (target / "README.md").write_text("depo", "utf-8")
        return "a" * 40

    monkeypatch.setattr(plugin_install, "_clone", fake_clone)
    market = tmp_path / "pazar"
    (market / ".claude-plugin").mkdir(parents=True)
    source = {"source": "git-subdir", "url": "ekip/monorepo", "path": "araclar/rapor"}
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "ekip",
                "owner": {"name": "E"},
                "plugins": [{"name": "rapor", "source": source}],
            }
        ),
        "utf-8",
    )
    plugin_install.add_marketplace(str(market))

    item = plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)

    assert calls == ["https://github.com/ekip/monorepo"]
    assert item.layout is not None and len(item.layout.skills) == 1
    assert not (item.layout.root / "README.md").exists()  # yalnız alt klasör kuruldu

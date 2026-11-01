"""`marketplace add` kaynak tablosu (SSH/http/url türü), `--scope`, `--sparse`, `--claudeai`.

#395, #381, #376. Ağ yok: klon ve indirme yamalanır.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store, trust
from fusion_cli.core.plugins import PluginError
from fusion_cli.tools import plugin_install, plugin_market_fetch, plugin_update
from fusion_cli.tools.plugin_market_source import KIND_GIT, KIND_URL, parse_market_source

runner = CliRunner()


def _market_files(folder: Path, name: str = "ekip") -> None:
    plugin = folder / "plugins" / "rapor"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "rapor"}', "utf-8")
    (plugin / "SKILL.md").write_text("---\nname: rapor\ndescription: R\n---\nR\n", "utf-8")
    (folder / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    entries = [{"name": "rapor", "source": "./plugins/rapor"}]
    (folder / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": name, "owner": {"name": "E"}, "plugins": entries}), "utf-8"
    )


@pytest.mark.parametrize(
    ("spec", "kind", "location", "ref"),
    [
        (
            "git@git.sirket.local:ekip/pazar.git",
            KIND_GIT,
            "git@git.sirket.local:ekip/pazar.git",
            "",
        ),
        ("git@github.com:o/r.git#v2", KIND_GIT, "git@github.com:o/r.git", "v2"),
        ("http://git.sirket.local/x.git", KIND_GIT, "http://git.sirket.local/x.git", ""),
        ("https://ornek.com/marketplace.json", KIND_URL, "https://ornek.com/marketplace.json", ""),
        ("http://ic.ag/pazar.json", KIND_URL, "http://ic.ag/pazar.json", ""),
    ],
)
def test_claude_kaynak_tablosu_ssh_http_url(spec, kind, location, ref):
    source = parse_market_source(spec)
    assert (source.kind, source.location, source.ref) == (kind, location, ref)


def test_ssh_ve_seyrek_kaynak_kullanici_git_ayarlariyla_klonlanir(monkeypatch):
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_user_clone(url, target, *, ref="", sparse=()):
        calls.append((url, tuple(sparse)))
        _market_files(target)
        return "a" * 40

    monkeypatch.setattr(plugin_market_fetch, "clone_user_source", fake_user_clone)
    result = runner.invoke(
        app,
        [
            "marketplace",
            "add",
            "git@git.sirket.local:ekip/pazar.git",
            "--sparse",
            ".claude-plugin",
            "plugins",
        ],
    )
    assert result.exit_code == 0, result.output
    record = plugin_store.load_state().marketplace("ekip")
    assert record.kind == KIND_GIT and record.sparse == (".claude-plugin", "plugins")
    assert calls == [("git@git.sirket.local:ekip/pazar.git", (".claude-plugin", "plugins"))]
    plugin_update.update_marketplace("ekip")  # seyrek yollar güncellemede korunur
    assert calls[-1][1] == (".claude-plugin", "plugins")


def test_seyrek_yalniz_git_pazarinda(tmp_path):
    _market_files(tmp_path / "pazar")
    result = runner.invoke(app, ["marketplace", "add", str(tmp_path / "pazar"), "--sparse", "x"])
    assert result.exit_code == 1 and "--sparse yalnız git" in result.output


def test_ic_ag_https_adresi_kullanici_kaynaginda_yerel_git_ile_klonlanir(monkeypatch):
    def private(url, target, *, ref="", sha=""):
        raise plugin_install.PrivateUrlError("iç ağ")

    used: list[str] = []

    def fake_user_clone(url, target, *, ref="", sparse=()):
        used.append(url)
        _market_files(target)
        return "b" * 40

    monkeypatch.setattr(plugin_install, "_clone", private)
    monkeypatch.setattr(plugin_market_fetch, "clone_user_source", fake_user_clone)
    record = plugin_install.add_marketplace("https://git.sirket.local/ekip/pazar.git")
    assert record.name == "ekip" and used == ["https://git.sirket.local/ekip/pazar.git"]


def test_url_turu_marketplace_json_indirilir_goreli_eklenti_kurulmaz(monkeypatch):
    body = {
        "name": "uzak",
        "owner": {"name": "U"},
        "plugins": [{"name": "rapor", "source": "./plugins/rapor"}],
    }
    monkeypatch.setattr(
        plugin_market_fetch, "_read_limited", lambda url: json.dumps(body).encode("utf-8")
    )
    record = plugin_install.add_marketplace("https://ornek.com/marketplace.json")
    assert (record.name, record.kind) == ("uzak", KIND_URL)
    assert plugin_update.update_marketplace("uzak").name == "uzak"
    with pytest.raises(PluginError, match="url türü"):
        plugin_install.install_plugin("rapor@uzak", approve=lambda _p: True)


def test_scope_project_extraknownmarketplaces_yazar_remove_siler(tmp_path, monkeypatch):
    market = tmp_path / "pazar"
    _market_files(market)
    project = tmp_path / "proje"
    project.mkdir()
    monkeypatch.chdir(project)
    trust.trust_project(project)

    added = runner.invoke(app, ["marketplace", "add", str(market), "--scope", "project", "--json"])

    assert added.exit_code == 0, added.output
    assert "project ayarlarında bildirildi" in added.output
    settings = json.loads((project / ".claude" / "settings.json").read_text("utf-8"))
    assert settings["extraKnownMarketplaces"] == {
        "ekip": {"source": {"source": "directory", "path": str(market.resolve())}}
    }
    gone = runner.invoke(app, ["marketplace", "remove", "ekip"])
    assert gone.exit_code == 0, gone.output
    settings = json.loads((project / ".claude" / "settings.json").read_text("utf-8"))
    assert settings["extraKnownMarketplaces"] == {}


def test_scope_gecersiz_ve_claudeai_desteklenmez(tmp_path):
    _market_files(tmp_path / "pazar")
    bad = runner.invoke(app, ["marketplace", "add", str(tmp_path / "pazar"), "--scope", "ekip"])
    assert bad.exit_code == 1
    assert plugin_store.load_state().marketplace("ekip") is None
    cloud = runner.invoke(app, ["marketplace", "add", "ekip", "--claudeai"])
    assert cloud.exit_code == 1 and "claude.ai" in cloud.output


def test_claude_kaynak_nesnesi():
    from fusion_cli.config.plugin_store import MarketplaceRecord
    from fusion_cli.tools.plugin_market_declare import claude_source

    github = MarketplaceRecord("a", "https://github.com/o/r#v1", "git", "/x")
    assert claude_source(github) == {"source": "github", "repo": "o/r", "ref": "v1"}
    ssh = MarketplaceRecord("a", "git@h:o/r.git", "git", "/x")
    assert claude_source(ssh) == {"source": "git", "url": "git@h:o/r.git"}
    url = MarketplaceRecord("a", "https://o.com/m.json", "url", "/x")
    assert claude_source(url) == {"source": "url", "url": "https://o.com/m.json"}


def test_list_data_size_veri_klasorunu_olcer(tmp_path):
    from fusion_cli.config.plugin_data import plugin_data_dir
    from fusion_cli.tools.plugin_listing import human_size

    _market_files(tmp_path / "pazar")
    plugin_install.add_marketplace(str(tmp_path / "pazar"))
    plugin_install.install_plugin("rapor@ekip", approve=lambda _p: True)
    (plugin_data_dir("rapor", create=True) / "b.bin").write_bytes(b"\0" * 5000)

    rows = json.loads(runner.invoke(app, ["list", "--json", "--data-size"]).output)
    assert rows[0]["dataDirSize"] == {"bytes": 5000, "human": "4.9KB"}
    named = json.loads(runner.invoke(app, ["list", "--json", "--data-size", "rapor@ekip"]).output)
    assert named[0]["dataDirSize"]["bytes"] == 5000
    missing = runner.invoke(app, ["list", "--json", "--data-size", "yok@ekip"])
    assert missing.exit_code == 1 and "kurulu olmayan" in missing.output
    plain = json.loads(runner.invoke(app, ["list", "--json"]).output)
    assert "dataDirSize" not in plain[0]
    assert (human_size(0), human_size(1023), human_size(3 * 1024 * 1024)) == (
        "0B",
        "1023B",
        "3.0MB",
    )

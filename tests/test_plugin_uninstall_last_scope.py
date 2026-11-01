"""Son kapsamdan kaldırma ve `install --config` (Claude Code `plugin uninstall`/`install`).

#408: kapsamlar kayıtta izlenir; eklenti son kapsamından kalkınca kopya, veri klasörü ve
userConfig değerleri/sırları silinir, başka kapsam kullanıyorsa paylaşılan kopya kalır.
#388/#381: `install --config key=value` şemaya göre doğrulanır; geçersizse kurulum geri alınır.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store, plugin_user_config, trust
from fusion_cli.config.plugin_data import plugin_data_dir

runner = CliRunner()

_SCHEMA = {
    "api_url": {"type": "string", "title": "API", "description": "Adres", "required": True},
    "api_token": {"type": "string", "title": "Token", "description": "T", "sensitive": True},
}


@pytest.fixture(autouse=True)
def _vault_key(monkeypatch):
    monkeypatch.setenv("FUSION_SECRET_KEY", "test-yalniz-eklenti-anahtari")


def _market(tmp_path: Path) -> Path:
    market = tmp_path / "pazar"
    plugin = market / "plugins" / "rapor"
    (plugin / ".claude-plugin").mkdir(parents=True)
    manifest = {"name": "rapor", "version": "1.0.0", "userConfig": _SCHEMA}
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), "utf-8")
    skill = plugin / "skills" / "ozet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8")
    (market / ".claude-plugin").mkdir(parents=True)
    entries = [{"name": "rapor", "source": "./plugins/rapor"}]
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "ekip", "owner": {"name": "E"}, "plugins": entries}), "utf-8"
    )
    return market


def _project(tmp_path: Path, monkeypatch, name: str = "proje") -> Path:
    project = tmp_path / name
    project.mkdir()
    monkeypatch.chdir(project)
    trust.trust_project(project)
    return project


def test_user_kaldirma_ayar_ve_sirlari_da_siler(tmp_path):
    runner.invoke(app, ["marketplace", "add", str(_market(tmp_path))])
    done = runner.invoke(
        app, ["install", "rapor@ekip", "--config", "api_url=https://x", "--config", "api_token=g"]
    )
    assert done.exit_code == 0, done.output
    base = plugin_store.plugins_dir()
    assert plugin_user_config.saved_values("rapor@ekip", base) == {
        "api_url": "https://x",
        "api_token": "g",
    }
    (plugin_data_dir("rapor@ekip", create=True) / "d.json").write_text("{}", "utf-8")

    gone = runner.invoke(app, ["uninstall", "rapor@ekip", "--keep-data"])

    assert gone.exit_code == 0, gone.output
    assert plugin_user_config.saved_values("rapor@ekip", base) == {}
    assert (plugin_data_dir("rapor@ekip") / "d.json").is_file()  # --keep-data yalnız veriyi korur


def test_baska_kapsam_kullaniyorsa_kopya_ve_ayar_kalir(tmp_path, monkeypatch):
    runner.invoke(app, ["marketplace", "add", str(_market(tmp_path))])
    project = _project(tmp_path, monkeypatch)
    assert runner.invoke(app, ["install", "rapor@ekip", "--config", "api_url=u"]).exit_code == 0
    assert runner.invoke(app, ["install", "rapor@ekip", "--scope", "project"]).exit_code == 0
    record = plugin_store.load_state().plugin("rapor")
    assert record.scopes == ("user", f"project:{project.resolve()}")

    first = runner.invoke(app, ["uninstall", "rapor@ekip"])  # yalnız user kapsamı

    assert first.exit_code == 0, first.output
    left = plugin_store.load_state().plugin("rapor")
    assert left is not None and left.scopes == (f"project:{project.resolve()}",)
    saved = plugin_user_config.saved_values("rapor@ekip", plugin_store.plugins_dir())
    assert saved == {"api_url": "u"}
    assert [i.record.name for i in plugin_store.active_plugins(root=project)] == ["rapor"]

    last = runner.invoke(app, ["uninstall", "rapor@ekip", "--scope", "project"])

    assert last.exit_code == 0, last.output
    assert plugin_store.load_state().plugin("rapor") is None
    assert plugin_user_config.saved_values("rapor@ekip", plugin_store.plugins_dir()) == {}


def test_kapsamsiz_kaldirma_yalniz_bu_projedeki_kurulumu_bulur(tmp_path, monkeypatch):
    runner.invoke(app, ["marketplace", "add", str(_market(tmp_path))])
    _project(tmp_path, monkeypatch)
    assert runner.invoke(app, ["install", "rapor@ekip", "--scope", "local"]).exit_code == 0

    done = runner.invoke(app, ["uninstall", "rapor", "--json"])

    assert done.exit_code == 0, done.output
    assert json.loads(done.output.strip().splitlines()[-1])["scope"] == "local"
    assert plugin_store.load_state().plugin("rapor") is None


def test_yalniz_projede_kurulu_eklenti_user_kapsamina_da_kurulur(tmp_path, monkeypatch):
    runner.invoke(app, ["marketplace", "add", str(_market(tmp_path))])
    _project(tmp_path, monkeypatch)
    runner.invoke(app, ["install", "rapor@ekip", "--scope", "project"])

    user = runner.invoke(app, ["install", "rapor@ekip"])

    assert user.exit_code == 0 and "kapsam: user" in user.output, user.output
    record = plugin_store.load_state().plugin("rapor")
    assert record.enabled is True and record.scopes[0] == "user"
    again = runner.invoke(app, ["install", "rapor@ekip"])
    assert "already installed (scope: user)" in again.output


def test_install_config_gecersizse_kurulum_geri_alinir(tmp_path):
    runner.invoke(app, ["marketplace", "add", str(_market(tmp_path))])

    bad = runner.invoke(app, ["install", "rapor@ekip", "--config", "yok=1", "--json"])

    assert bad.exit_code == 1, bad.output
    payload = json.loads(bad.output.strip().splitlines()[-1])
    assert payload["outcome"] == "failed" and "yok" in payload["message"]
    assert plugin_store.load_state().plugin("rapor") is None
    nopair = runner.invoke(app, ["install", "rapor@ekip", "--config", "api_url"])
    assert nopair.exit_code == 1 and "anahtar=değer" in nopair.output
    mcpb = runner.invoke(app, ["install", "rapor@ekip", "--config", "srv.key=1"])
    assert mcpb.exit_code == 1 and ".mcpb" in mcpb.output


def test_install_zorunlu_secenek_eksikse_configure_ipucu(tmp_path):
    runner.invoke(app, ["marketplace", "add", str(_market(tmp_path))])
    done = runner.invoke(app, ["install", "rapor@ekip"])
    assert done.exit_code == 0, done.output
    flat = " ".join(done.output.split())
    assert "Ayarlanmamış zorunlu seçenekler: api_url" in flat
    assert "fusion plugin configure rapor@ekip" in flat


def test_validate_gecersiz_userconfig_semasini_hata_sayar(tmp_path):
    root = tmp_path / "e"
    (root / ".claude-plugin").mkdir(parents=True)
    bad = {"name": "rapor", "version": "1", "userConfig": {"a": {"type": "renk"}}}
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps(bad), "utf-8")
    result = runner.invoke(app, ["validate", str(root)])
    assert result.exit_code == 1, result.output
    assert "userConfig.a" in result.output

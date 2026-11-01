"""`extraKnownMarketplaces` (takma ad `additionalMarketplaces`) project/local bildirimi (#376).

Claude Code (https://code.claude.com/docs/en/settings-reference.md "extraKnownMarketplaces"):
depo `.claude/settings.json`/`.claude/settings.local.json` girdileri yalnız klasöre güvenildikten
sonra uygulanır; aynı adlı girdide en yüksek öncelikli dosyanınki BÜTÜNÜYLE geçerlidir; bilinmeyen
pazar kaydedilir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store, trust
from fusion_cli.tools import plugin_declared

runner = CliRunner()


def _market(folder: Path, name: str) -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": name, "owner": {"name": "Ekip"}, "plugins": []}), encoding="utf-8"
    )
    return folder


def _declare(project: Path, file: str, entries: dict[str, object], key: str = "") -> None:
    path = project / ".claude" / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({key or plugin_declared.DECLARED_KEY: entries}), encoding="utf-8")


def _dir_entry(path: Path) -> dict[str, object]:
    return {"source": {"source": "directory", "path": str(path)}}


def _known() -> list[str]:
    return [item.name for item in plugin_store.load_state().marketplaces]


def test_guvenilmeyen_projenin_bildirimi_sessizce_yok_sayilir(tmp_path):
    project = tmp_path / "proje"
    _declare(project, "settings.json", {"ekip": _dir_entry(_market(tmp_path / "m", "ekip"))})
    assert plugin_declared.declared_marketplaces(project) == {}
    assert plugin_declared.sync_declared(project) == ()
    assert _known() == []


def test_guvenilen_projenin_bilinmeyen_pazari_eklenir_bilineni_tekrar_eklenmez(tmp_path):
    project = tmp_path / "proje"
    _declare(project, "settings.json", {"ekip": _dir_entry(_market(tmp_path / "m", "ekip"))})
    trust.trust_project(project)
    assert plugin_declared.sync_declared(project) == ("ekip",)
    assert _known() == ["ekip"]
    assert plugin_declared.sync_declared(project) == ()


def test_local_ayni_adli_girdiyi_butunuyle_ezer(tmp_path):
    project = tmp_path / "proje"
    first = _market(tmp_path / "bir", "ekip")
    second = _market(tmp_path / "iki", "ekip")
    _declare(project, "settings.json", {"ekip": _dir_entry(first)})
    _declare(project, "settings.local.json", {"ekip": {**_dir_entry(second), "autoUpdate": True}})
    trust.trust_project(project)
    found = plugin_declared.declared_marketplaces(project)["ekip"]
    assert found.scope == "local"
    assert found.spec == str(second)
    assert found.auto_update is True


def test_takma_ad_okunur_ikisi_birden_varsa_asil_anahtar_kazanir(tmp_path):
    project = tmp_path / "proje"
    alias_only = {"takma": _dir_entry(_market(tmp_path / "t", "takma"))}
    _declare(project, "settings.json", alias_only, key=plugin_declared.ALIAS_KEY)
    trust.trust_project(project)
    assert list(plugin_declared.declared_marketplaces(project)) == ["takma"]

    both = {
        plugin_declared.DECLARED_KEY: {"asil": _dir_entry(_market(tmp_path / "a", "asil"))},
        plugin_declared.ALIAS_KEY: alias_only,
    }
    (project / ".claude" / "settings.json").write_text(json.dumps(both), encoding="utf-8")
    trust.trust_project(project)
    assert list(plugin_declared.declared_marketplaces(project)) == ["asil"]


@pytest.mark.parametrize(
    ("source", "spec"),
    [
        ({"source": "github", "repo": "acme/eklentiler"}, "acme/eklentiler"),
        ({"source": "github", "repo": "acme/eklentiler", "ref": "v2"}, "acme/eklentiler#v2"),
        (
            {"source": "git", "url": "https://git.example.com/a/b.git"},
            "https://git.example.com/a/b.git",
        ),
        ({"source": "directory", "path": "./pazar"}, "{root}/pazar"),
        ({"source": "file", "path": "pazar/m.json"}, "{root}/pazar/m.json"),
    ],
)
def test_kaynak_turleri_pazar_ekleme_kaynagina_cevrilir(tmp_path, source, spec):
    assert plugin_declared.source_spec(source, tmp_path) == spec.format(root=tmp_path)


@pytest.mark.parametrize(
    "source",
    [
        {"source": "url"},
        {"source": "settings", "name": "x", "plugins": []},
        {"source": "github"},
        "acme/eklentiler",
    ],
)
def test_desteklenmeyen_ya_da_bozuk_kaynak_atlanir(tmp_path, source):
    assert plugin_declared.source_spec(source, tmp_path) is None


def test_url_turu_bildirim_adres_olarak_eklenir(tmp_path):
    """#395: Claude url türü (marketplace.json adresi) artık Fusion'da da var."""
    source = {"source": "url", "url": "https://example.com/marketplace.json"}
    assert plugin_declared.source_spec(source, tmp_path) == "https://example.com/marketplace.json"


def test_eklenemeyen_pazar_digerlerini_durdurmaz(tmp_path, caplog):
    project = tmp_path / "proje"
    _declare(
        project,
        "settings.json",
        {
            "yok": _dir_entry(tmp_path / "olmayan"),
            "ekip": _dir_entry(_market(tmp_path / "m", "ekip")),
        },
    )
    trust.trust_project(project)
    assert plugin_declared.sync_declared(project) == ("ekip",)
    assert "yok" in caplog.text


def test_cli_marketplace_list_bildirilen_pazari_once_ekler(tmp_path, monkeypatch):
    project = tmp_path / "proje"
    _declare(project, "settings.json", {"ekip": _dir_entry(_market(tmp_path / "m", "ekip"))})
    trust.trust_project(project)
    monkeypatch.chdir(project)
    result = runner.invoke(app, ["marketplace", "list"])
    assert result.exit_code == 0, result.output
    assert "ekip" in result.output


def test_bildirim_adi_kaynaktaki_addan_farkliysa_her_cagride_yeniden_eklenmez(tmp_path):
    project = tmp_path / "proje"
    _declare(project, "settings.json", {"farkli": _dir_entry(_market(tmp_path / "m", "ekip"))})
    trust.trust_project(project)

    assert plugin_declared.sync_declared(project) == ("ekip",)
    assert plugin_declared.sync_declared(project) == ()
    assert _known() == ["ekip"]

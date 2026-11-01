"""`--plugin-dir` / CLAUDE_CODE_PLUGIN_DIRS oturumluk eklentileri (#401)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from fusion_cli.cli.app import app as root_app
from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store
from fusion_cli.config.plugin_session import SESSION_ENV
from fusion_cli.tools import plugin_install
from fusion_cli.tools.plugin_capabilities import with_plugin_root

runner = CliRunner()


def _plugin(folder: Path, name: str, version: str = "2.0.0") -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": name, "version": version}), encoding="utf-8"
    )
    skill = folder / "skills" / "ozet"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Özetle\n---\nKök: ${CLAUDE_PLUGIN_ROOT}\n",
        encoding="utf-8",
    )
    return folder


def test_plugin_dir_oturumluk_inline_ve_kurulu_ayni_adi_ezer(tmp_path, monkeypatch):
    plugin_install.install_plugin(
        str(_plugin(tmp_path / "kurulu", "rapor", "1.0.0")), approve=lambda _p: True
    )
    session = _plugin(tmp_path / "gelistirme", "rapor")
    monkeypatch.setenv(SESSION_ENV, str(session))

    active = plugin_store.active_plugins()

    assert [(i.record.name, i.record.marketplace) for i in active] == [("rapor", "inline")]
    assert active[0].record.exec_approved is True
    body = with_plugin_root("${CLAUDE_PLUGIN_ROOT}", session / "skills" / "ozet" / "SKILL.md")
    assert body == str(session.resolve())


def test_eklenti_klasoru_klasoru_cocuklarini_yukler(tmp_path, monkeypatch):
    _plugin(tmp_path / "hepsi" / "a", "a")
    _plugin(tmp_path / "hepsi" / "b", "b")
    monkeypatch.setenv(SESSION_ENV, str(tmp_path / "hepsi"))
    assert sorted(i.record.name for i in plugin_store.active_plugins()) == ["a", "b"]


def test_cli_plugin_dir_list_json_ve_details(tmp_path, monkeypatch):
    monkeypatch.setenv(SESSION_ENV, "")
    session = _plugin(tmp_path / "gelistirme", "rapor")

    listed = runner.invoke(root_app, ["--plugin-dir", str(session), "plugin", "list", "--json"])

    assert listed.exit_code == 0, listed.output
    rows = json.loads(listed.output)
    assert rows == [
        {
            "id": "rapor@inline",
            "version": "2.0.0",
            "scope": "session",
            "enabled": True,
            "installPath": str(session.resolve()),
        }
    ]
    text = runner.invoke(app, ["list"]).output
    assert "Session-only plugins (--plugin-dir / --plugin-url):" in text
    assert "rapor@inline 2.0.0" in text
    shown = runner.invoke(app, ["details", "rapor@inline"])
    assert shown.exit_code == 0 and "Skills: 1" in shown.output


def test_bozuk_zip_ve_olmayan_yol_atlanir(tmp_path, monkeypatch, caplog):
    import os

    (tmp_path / "x.zip").write_bytes(b"zip degil")
    monkeypatch.setenv(
        SESSION_ENV, os.pathsep.join([str(tmp_path / "x.zip"), str(tmp_path / "yok")])
    )
    assert plugin_store.active_plugins() == ()
    assert "geçerli bir .zip" in caplog.text and "klasör bulunamadı" in caplog.text


def _zip(tmp_path: Path, members: dict[str, str]) -> Path:
    import zipfile

    path = tmp_path / "eklenti.zip"
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return path


def test_plugin_dir_zip_arsivini_acip_inline_yukler(tmp_path, monkeypatch):
    """Claude `--plugin-dir`: "Load a plugin from a directory or .zip" (#401)."""
    manifest = json.dumps({"name": "rapor", "version": "3.0.0"})
    archive = _zip(
        tmp_path,
        {
            "rapor/.claude-plugin/plugin.json": manifest,
            "rapor/skills/ozet/SKILL.md": "---\nname: ozet\ndescription: Ö\n---\nÖ\n",
        },
    )
    monkeypatch.setenv(SESSION_ENV, str(archive))
    active = plugin_store.active_plugins()
    assert [(i.record.name, i.record.marketplace, i.record.version) for i in active] == [
        ("rapor", "inline", "3.0.0")
    ]
    assert plugin_store.active_plugins()[0].record.source == active[0].record.source  # önbellek


def test_zip_yol_disina_cikan_girdi_reddedilir(tmp_path, monkeypatch, caplog):
    archive = _zip(tmp_path, {"../kacak.txt": "x", ".claude-plugin/plugin.json": "{}"})
    monkeypatch.setenv(SESSION_ENV, str(archive))
    assert plugin_store.active_plugins() == ()
    assert "güvensiz girdi" in caplog.text
    assert not (tmp_path / "kacak.txt").exists()


def test_plugin_url_zipi_indirip_oturumluk_yukler(tmp_path, monkeypatch):
    """Claude `--plugin-url`: "Fetch a plugin .zip from a URL for this session only"."""
    from fusion_cli.config import plugin_archive

    manifest = json.dumps({"name": "uzak", "version": "1.0.0"})
    source = _zip(tmp_path, {".claude-plugin/plugin.json": manifest, "SKILL.md": "x"})
    seen: list[str] = []

    def fake_download(url: str, target: Path) -> None:
        seen.append(url)
        target.write_bytes(source.read_bytes())

    monkeypatch.setattr(plugin_archive, "_download", fake_download)
    monkeypatch.setenv(SESSION_ENV, "")
    url = "https://ornek.test/uzak.zip"
    listed = runner.invoke(root_app, ["--plugin-url", url, "plugin", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    assert [row["id"] for row in json.loads(listed.output)] == ["uzak@inline"]
    assert seen == [url]
    bad = runner.invoke(root_app, ["--plugin-url", "file:///etc/x.zip", "plugin", "list"])
    assert bad.exit_code == 0  # uyarıyla atlanır


def test_ayarda_inline_false_oturumluk_eklentiyi_kapatir_kurulu_kopya_yuklenir(
    tmp_path, monkeypatch
):
    """Claude: `"<ad>@inline": false` oturumluk eklentiyi kapatır; gölgelemez (#401)."""
    plugin_install.install_plugin(
        str(_plugin(tmp_path / "kurulu", "rapor", "1.0.0")), approve=lambda _p: True
    )
    monkeypatch.setenv(SESSION_ENV, str(_plugin(tmp_path / "gelistirme", "rapor")))
    project = tmp_path / "proje"
    local = project / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local.write_text(json.dumps({"enabledPlugins": {"rapor@inline": False}}), encoding="utf-8")

    active = plugin_store.active_plugins(root=project)

    assert [(i.record.name, i.record.marketplace) for i in active] == [("rapor", "")]


def test_defaultenabled_false_oturumluk_eklenti_yuklenmez(tmp_path, monkeypatch):
    folder = _plugin(tmp_path / "gelistirme", "rapor")
    manifest = folder / ".claude-plugin" / "plugin.json"
    manifest.write_text(json.dumps({"name": "rapor", "defaultEnabled": False}), "utf-8")
    monkeypatch.setenv(SESSION_ENV, str(folder))
    assert plugin_store.active_plugins(root=tmp_path / "proje") == ()

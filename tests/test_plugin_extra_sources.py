"""Pazar girdisinin archive / npm / command eklenti kaynakları ve komut onayı (#399, #381)."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store
from fusion_cli.core.plugins import parse_marketplace
from fusion_cli.tools import plugin_install, plugin_source_fetch, plugin_update
from fusion_cli.tools.plugin_source_fetch import CommandRefusedError


@pytest.fixture(autouse=True)
def _ev(tmp_path, monkeypatch):
    home = tmp_path / "ev"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("npm_config_cache", str(tmp_path / "npm-cache"))


def _plugin(folder: Path, name: str = "uret", version: str = "") -> Path:
    (folder / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    manifest = {"name": name, **({"version": version} if version else {})}
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest), "utf-8")
    (folder / "skills" / "ozet").mkdir(parents=True, exist_ok=True)
    (folder / "skills" / "ozet" / "SKILL.md").write_text(
        "---\nname: ozet\ndescription: Ö\n---\nÖ\n", "utf-8"
    )
    return folder


def _market(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    market = tmp_path / "pazar"
    (market / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    data = {"name": "ekip", "owner": {"name": "E"}, "plugins": entries}
    (market / ".claude-plugin" / "marketplace.json").write_text(json.dumps(data), "utf-8")
    return market


def test_kaynak_turleri_claude_kurallariyla_ayristirilir():
    raw = {
        "name": "ekip",
        "owner": {"name": "E"},
        "plugins": [
            {"name": "a", "source": {"source": "archive", "url": "https://x.example/a.zip"}},
            {"name": "b", "source": {"source": "npm", "package": "@acme/b", "version": "^1"}},
            {"name": "c", "source": {"source": "command", "command": "echo /x", "mode": "link"}},
            {"name": "d", "source": {"source": "archive", "url": "http://x.example/d.zip"}},
            {"name": "e", "source": {"source": "archive", "url": "https://127.0.0.1/e.zip"}},
            {"name": "f", "source": {"source": "command", "command": "a    b"}},
            {"name": "g", "source": {"source": "command", "command": "x", "timeout": 601}},
            {
                "name": "h",
                "source": {"source": "archive", "url": "https://x.example/h.zip"},
                "headersHelper": "echo {}",
            },
            {"name": "i", "source": "./i", "headers": {"A": "b"}},
        ],
    }

    market = parse_marketplace(raw)

    kinds = {e.name: e.source.kind for e in market.entries}
    assert kinds == {"a": "archive", "b": "npm", "c": "command", "i": "path"}
    b = next(e for e in market.entries if e.name == "b")
    assert (b.source.location, b.source.ref) == ("@acme/b", "^1")
    text = "\n".join(market.warnings)
    for skipped in ("plugins[3]", "plugins[4]", "plugins[5]", "plugins[6]", "plugins[7]"):
        assert skipped in text
    assert 'Plugin "i" sets headers/headersHelper' in text


def _command_market(tmp_path: Path, printed: Path, mode: str = "copy") -> None:
    source = {"source": "command", "command": f"echo {printed}", "mode": mode}
    plugin_install.add_marketplace(str(_market(tmp_path, [{"name": "uret", "source": source}])))


def test_command_kaynagi_onaysiz_calismaz_onayla_kopyalanir(tmp_path):
    printed = _plugin(tmp_path / "cikti")
    _command_market(tmp_path, printed)

    with pytest.raises(CommandRefusedError) as refused:
        plugin_install.install_plugin("uret@ekip", approve=lambda _p: True)
    assert refused.value.shown.command == f"echo {printed}"
    assert plugin_store.load_state().plugin("uret") is None

    item = plugin_install.install_plugin(
        "uret@ekip", approve=lambda _p: True, accept_command=lambda _s: True
    )

    folder = plugin_store.plugin_folder(item.record)
    assert folder != printed and (folder / "skills" / "ozet" / "SKILL.md").is_file()
    assert len(item.record.version) == 12  # içerik karması sürüm kimliği
    assert item.record.accepted_command == f"copy echo {printed}"


def test_command_link_kipinde_klasor_yerinde_yuklenir(tmp_path):
    printed = _plugin(tmp_path / "cikti")
    _command_market(tmp_path, printed, mode="link")

    item = plugin_install.install_plugin(
        "uret@ekip", approve=lambda _p: True, accept_command=lambda _s: True
    )

    assert Path(item.record.folder) == printed


def test_cli_json_shown_command_ve_accept_command(tmp_path):
    printed = _plugin(tmp_path / "cikti")
    _command_market(tmp_path, printed)
    runner = CliRunner()

    refused = runner.invoke(app, ["install", "uret@ekip", "--json"])

    assert refused.exit_code == 1
    payload = json.loads(refused.output.strip().splitlines()[-1])
    assert payload["failureCode"] == "command_source_refused"
    shown = payload["shownCommand"]
    assert shown["kind"] == "command_source" and shown["mode"] == "copy"
    wrong = runner.invoke(app, ["install", "uret@ekip", "--accept-command", "0" * 64])
    assert wrong.exit_code == 1
    ok = runner.invoke(app, ["install", "uret@ekip", "--accept-command", shown["sha256"]])
    assert ok.exit_code == 0, ok.output
    assert plugin_store.load_state().plugin("uret") is not None


def test_cli_yes_ve_accept_command_birlikte_hata(tmp_path):
    _command_market(tmp_path, _plugin(tmp_path / "cikti"))

    out = CliRunner().invoke(app, ["install", "uret@ekip", "-y", "--accept-command", "a" * 64])

    assert out.exit_code == 1 and "birlikte" in out.output


def test_guncellemede_ayni_komut_yeniden_sorulmaz(tmp_path):
    printed = _plugin(tmp_path / "cikti", version="1.0.0")
    _command_market(tmp_path, printed)
    plugin_install.install_plugin(
        "uret@ekip", approve=lambda _p: True, accept_command=lambda _s: True
    )
    _plugin(printed, version="1.1.0")

    result = plugin_update.update_plugin("uret", approve=lambda _p: True)

    assert result.changed and result.record.version == "1.1.0"


def _zip(folder: Path, target: Path) -> bytes:
    with zipfile.ZipFile(target, "w") as archive:
        for path in folder.rglob("*"):
            archive.write(path, Path("sarmal") / path.relative_to(folder))
    return target.read_bytes()


def _fake_download(data: bytes):
    def download(url, headers, target):
        target.write_bytes(data)
        download.headers = dict(headers)
        return hashlib.sha256(data).hexdigest()

    return download


def test_archive_kaynagi_indirilir_ozet_dogrulanir_surum_ozetten(tmp_path, monkeypatch):
    data = _zip(_plugin(tmp_path / "kaynak"), tmp_path / "a.zip")
    digest = hashlib.sha256(data).hexdigest()
    fake = _fake_download(data)
    monkeypatch.setattr(plugin_source_fetch, "_download", fake)
    entry = {
        "name": "uret",
        "source": {"source": "archive", "url": "https://x.example/a.zip", "sha256": digest},
        "headers": {"Authorization": "Bearer t"},
    }
    plugin_install.add_marketplace(str(_market(tmp_path, [entry])))

    item = plugin_install.install_plugin("uret@ekip", approve=lambda _p: True)

    assert item.record.version == digest[:12]
    assert fake.headers == {"Authorization": "Bearer t"}
    assert (plugin_store.plugin_folder(item.record) / ".claude-plugin").is_dir()


def test_archive_ozet_uyusmazsa_kurulmaz(tmp_path, monkeypatch):
    data = _zip(_plugin(tmp_path / "kaynak"), tmp_path / "a.zip")
    monkeypatch.setattr(plugin_source_fetch, "_download", _fake_download(data))
    source = {"source": "archive", "url": "https://x.example/a.zip", "sha256": "a" * 64}
    plugin_install.add_marketplace(str(_market(tmp_path, [{"name": "uret", "source": source}])))

    with pytest.raises(plugin_install.PluginError, match="özeti uyuşmuyor"):
        plugin_install.install_plugin("uret@ekip", approve=lambda _p: True)


def test_archive_headers_helper_onay_ister(tmp_path, monkeypatch):
    data = _zip(_plugin(tmp_path / "kaynak"), tmp_path / "a.zip")
    fake = _fake_download(data)
    monkeypatch.setattr(plugin_source_fetch, "_download", fake)
    entry = {
        "name": "uret",
        "strict": False,
        "source": {"source": "archive", "url": "https://x.example/a.zip"},
        "headersHelper": """echo '{"X-Token": "gizli"}'""",
    }
    plugin_install.add_marketplace(str(_market(tmp_path, [entry])))

    with pytest.raises(CommandRefusedError) as refused:
        plugin_install.install_plugin("uret@ekip", approve=lambda _p: True)
    assert refused.value.shown.kind == "entry_helper"
    plugin_install.install_plugin(
        "uret@ekip", approve=lambda _p: True, accept_command=lambda _s: True
    )
    assert fake.headers == {"X-Token": "gizli"}


@pytest.mark.skipif(shutil.which("npm") is None, reason="npm yok")
def test_npm_kaynagi_betik_calistirmadan_paketten_kurulur(tmp_path):
    package = _plugin(tmp_path / "paket")
    (package / "package.json").write_text(
        json.dumps({"name": "uret", "version": "2.0.0", "scripts": {"prepack": "touch HACK"}}),
        "utf-8",
    )
    entry = {"name": "uret", "source": {"source": "npm", "package": str(package)}}
    plugin_install.add_marketplace(str(_market(tmp_path, [entry])))

    item = plugin_install.install_plugin("uret@ekip", approve=lambda _p: True)

    folder = plugin_store.plugin_folder(item.record)
    assert (folder / "skills" / "ozet" / "SKILL.md").is_file()
    assert not (package / "HACK").exists()
    assert item.record.version == "unknown"


def test_json_hata_failure_code_not_installed():
    out = CliRunner().invoke(app, ["disable", "yok", "--json"])

    payload = json.loads(out.output.strip().splitlines()[-1])
    assert payload["failureCode"] == "not_installed"


def test_masaustu_rpc_komut_onayi_ister_ve_ozetle_kurar(tmp_path):
    from fusion_cli.appserver import extension_routes

    _command_market(tmp_path, _plugin(tmp_path / "cikti"))

    first = extension_routes._install({"kaynak": "uret@ekip"})

    assert first["komut_onayi_gerekli"] is True
    sha = first["komut"]["sha256"]
    second = extension_routes._install({"kaynak": "uret@ekip", "komut_onayi": sha})
    assert second["ok"] is True


def test_repl_install_yes_komutu_onaylar(tmp_path):
    from fusion_cli.cli.repl import plugin_command

    _command_market(tmp_path, _plugin(tmp_path / "cikti"))

    refused = plugin_command._install(None, ["uret@ekip", "--scope", "user"], False, False)
    assert "--accept-command" in refused
    done = plugin_command._install(None, ["uret@ekip", "--scope", "user"], True, False)
    assert "uret@ekip" in done and plugin_store.load_state().plugin("uret") is not None

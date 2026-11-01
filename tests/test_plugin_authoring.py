"""`plugin init|new`, `tag`, `test` ve `<ad>@skills-dir` eklentileri (Claude Code, #380, #401).

Beklenen davranış Claude Code 2.1.287'de geçici HOME ile ölçüldü (init iskeleti, list çıktısı,
disable'ın ~/.claude/settings.json'a yazması, tag hata/başarı metinleri).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fusion_cli.cli.plugin_commands import app
from fusion_cli.config import plugin_store
from fusion_cli.tools.capabilities import CapabilityRegistry

runner = CliRunner()


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "ev"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: folder))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(folder / ".gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    project = tmp_path / "proje"
    project.mkdir()
    monkeypatch.chdir(project)
    return folder


def _manifest(home: Path, name: str) -> dict:
    path = home / ".claude" / "skills" / name / ".claude-plugin" / "plugin.json"
    return json.loads(path.read_text("utf-8"))


def test_init_claude_iskeletini_kurar(home):
    done = runner.invoke(
        app,
        ["init", "yardimci", "--author", "Ali", "--author-email", "a@b.c", "--description", "Y"],
    )
    assert done.exit_code == 0, done.output
    assert "yardimci@skills-dir" in done.output
    assert _manifest(home, "yardimci") == {
        "$schema": "https://anthropic.com/claude-code/plugin.schema.json",
        "name": "yardimci",
        "version": "0.1.0",
        "description": "Y",
        "author": {"name": "Ali", "email": "a@b.c"},
        "skills": ["./"],
    }
    root = home / ".claude" / "skills" / "yardimci"
    assert sorted(p.name for p in root.iterdir()) == [".claude-plugin", "SKILL.md"]
    again = runner.invoke(app, ["init", "yardimci"])
    assert again.exit_code == 1 and "--force" in again.output
    assert runner.invoke(app, ["init", "yardimci", "--force", "--author", "A"]).exit_code == 0


def test_init_with_degisken_sayida_bilesen_ve_ad_hatalari(home):
    done = runner.invoke(
        app, ["new", "tam", "--author", "A", "--with", "skills", "agents", "hooks", "mcp", "lsp"]
    )
    assert done.exit_code == 0, done.output
    root = home / ".claude" / "skills" / "tam"
    for rel in ("skills/example/SKILL.md", "agents/example.md", "hooks/hooks.json", ".mcp.json"):
        assert (root / rel).is_file(), rel
    assert (root / ".lsp.json").is_file()
    channel = runner.invoke(app, ["init", "kanal", "--author", "A", "--with", "channel"])
    assert channel.exit_code == 0
    assert _manifest(home, "kanal")["channels"] == [{"server": "kanal", "displayName": "kanal"}]
    for bad, text in (("claude-x", "ayrılmış"), ("../x", "yol ayırıcı"), ("a b", "boşluk")):
        result = runner.invoke(app, ["init", bad])
        assert result.exit_code == 1 and text in result.output, (bad, result.output)
    warned = runner.invoke(app, ["init", "Kotu_Ad"])
    assert warned.exit_code == 0 and "kebab-case" in warned.output and "author" in warned.output


def test_skills_dir_eklentisi_kurulmadan_onekli_yuklenir_ve_kapatilir(home):
    runner.invoke(app, ["init", "yardimci", "--author", "A", "--with", "skills"])
    project = Path.cwd()

    active = [plugin_store.plugin_id(i.record) for i in plugin_store.active_plugins(root=project)]
    assert active == ["yardimci@skills-dir"]
    names = {c.name for c in CapabilityRegistry(home, project).skills()}
    assert "yardimci:example" in names and "example" not in names  # düz beceri olarak değil

    listed = runner.invoke(app, ["list"])
    assert "Skills-directory plugins (.claude/skills/*):" in listed.output
    rows = json.loads(runner.invoke(app, ["list", "--json"]).output)
    assert rows == [
        {
            "id": "yardimci@skills-dir",
            "version": "0.1.0",
            "scope": "user",
            "enabled": True,
            "installPath": str((home / ".claude" / "skills" / "yardimci").resolve()),
        }
    ]
    off = runner.invoke(app, ["disable", "yardimci@skills-dir"])
    assert off.exit_code == 0, off.output
    settings = json.loads((home / ".claude" / "settings.json").read_text("utf-8"))
    assert settings["enabledPlugins"] == {"yardimci@skills-dir": False}
    assert plugin_store.active_plugins(root=project) == ()
    assert runner.invoke(app, ["disable", "yardimci@skills-dir"]).exit_code == 1
    assert runner.invoke(app, ["enable", "yardimci@skills-dir"]).exit_code == 0
    assert "Skills: 2" in runner.invoke(app, ["details", "yardimci@skills-dir"]).output


def _git(folder: Path, *args: str) -> str:
    env_args = ["-c", "user.name=t", "-c", "user.email=t@t"]
    done = subprocess.run(
        ["git", "-C", str(folder), *env_args, *args], capture_output=True, text=True, check=True
    )
    return done.stdout


def _repo(home: Path, name: str = "yardimci") -> Path:
    runner.invoke(app, ["init", name, "--author", "A"])
    root = home / ".claude" / "skills" / name
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "i")
    return root


def test_tag_deneme_olusturma_ve_hatalar(home):
    root = _repo(home)
    dry = runner.invoke(app, ["tag", str(root), "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "Tag:     yardimci--v0.1.0" in dry.output and "push origin" in dry.output
    assert _git(root, "tag") == ""

    made = runner.invoke(app, ["tag", str(root), "-m", "sürüm %s"])
    assert made.exit_code == 0, made.output
    assert _git(root, "tag").split() == ["yardimci--v0.1.0"]
    assert "sürüm 0.1.0" in _git(root, "tag", "-n1")
    again = runner.invoke(app, ["tag", str(root)])
    assert again.exit_code == 1 and "zaten var" in again.output

    (root / "yeni.txt").write_text("x", "utf-8")
    dirty = runner.invoke(app, ["tag", str(root), "--dry-run"])
    assert dirty.exit_code == 1 and "yeni.txt" in dirty.output
    missing = runner.invoke(app, ["tag", str(home / "yok")])
    assert missing.exit_code == 1 and "Yol bulunamadı" in missing.output


def test_tag_pazar_girdisi_surumu_celisirse_reddeder(home, tmp_path):
    market = tmp_path / "pazar"
    plugin = market / "plugins" / "rapor"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "rapor", "version": "0.1.0"}), "utf-8"
    )
    (market / ".claude-plugin").mkdir(parents=True)
    entry = {"name": "rapor", "source": "./plugins/rapor", "version": "0.2.0"}
    (market / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "m", "owner": {"name": "o"}, "plugins": [entry]}), "utf-8"
    )
    _git(market, "init", "-q")
    result = runner.invoke(app, ["tag", str(plugin)])
    assert result.exit_code == 1 and "Sürüm uyuşmuyor" in result.output
    noversion = tmp_path / "surumsuz"
    (noversion / ".claude-plugin").mkdir(parents=True)
    (noversion / ".claude-plugin" / "plugin.json").write_text('{"name": "s"}', "utf-8")
    assert "version" in runner.invoke(app, ["tag", str(noversion)]).output


def test_plugin_test_fusionda_desteklenmiyor(home):
    result = runner.invoke(app, ["test"])
    assert result.exit_code == 1 and "mod sistemi" in result.output

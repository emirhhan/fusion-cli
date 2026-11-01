"""`--bare` kataloğu: kullanıcı/proje becerileri keşfedilmez, --add-dir becerileri yüklenir (#298)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.cli.print_runtime import bare_catalog
from fusion_cli.config.loader import load_config


def _skill(base: Path, name: str) -> None:
    folder = base / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: deneme\n---\ngövde\n", encoding="utf-8"
    )


def test_bare_proje_ve_kullanici_becerilerini_atlar(monkeypatch, tmp_path):
    home, project, extra = tmp_path / "ev", tmp_path / "proje", tmp_path / "ek"
    for path in (home, project, extra):
        path.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(project)
    _skill(home, "kullanici-beceri")
    _skill(project, "proje-beceri")
    _skill(extra, "ek-beceri")
    names = {item.name for item in bare_catalog(load_config(), (extra,)).skills()}
    assert "ek-beceri" in names
    assert "proje-beceri" not in names and "kullanici-beceri" not in names


def test_bare_mcp_config_sunucusu_baglanir_araclari_acik(monkeypatch):
    from types import SimpleNamespace

    from typer.testing import CliRunner

    from fusion_cli.cli import app as app_module
    from fusion_cli.cli import print_run

    calls: list[dict] = []

    async def _fake(task, config, **kwargs):
        calls.append({"config": config, **kwargs})
        return SimpleNamespace(
            final_text="t", ok=True, stop_reason=None, model_calls_made=1,
            hit_step_limit=False, messages=[],
        )

    monkeypatch.setattr(print_run, "run_agent_task", _fake)
    raw = '{"mcpServers": {"dosya": {"command": "npx", "args": ["x"]}}}'
    result = CliRunner().invoke(app_module.app, ["-p", "x", "--bare", "--mcp-config", raw])
    assert result.exit_code == 0, result.output
    assert [s.name for s in calls[0]["config"].mcp_servers] == ["dosya"]
    assert "dosya__*" in calls[0]["allowed_tools"]

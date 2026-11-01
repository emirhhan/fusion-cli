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

"""Becerinin `paths` alanı: eşleşen dosyaya erişilene kadar listede yok (Claude Code #161)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.engines.agent import skill_paths
from fusion_cli.engines.agent.skill_index import skill_index_block
from fusion_cli.tools.capabilities import CapabilityRegistry


def _skill(home: Path, name: str, extra: str) -> None:
    folder = home / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name} açıklaması\n{extra}---\ngövde", encoding="utf-8"
    )


def test_paths_becerisi_eslesen_dosyaya_erisince_etkinlesir(tmp_path: Path) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    (root / "src").mkdir(parents=True)
    _skill(home, "react", "paths: src/**/*.tsx, *.css\n")
    _skill(home, "genel", "")
    registry = CapabilityRegistry(home, root)

    before = skill_index_block(registry, 10_000)
    assert "genel" in before and "react" not in before

    assert skill_paths.activate_for(registry, root, (root / "README.md",)) is None
    note = skill_paths.activate_for(registry, root, (root / "src" / "a" / "App.tsx",))

    assert note is not None and "react" in note.content
    assert "react" in skill_index_block(registry, 10_000)
    # Bir kez duyurulur; dışarıdaki dosya eşleşmez.
    assert skill_paths.activate_for(registry, root, (root / "src" / "B.tsx",)) is None


def test_calisma_dizini_disindaki_dosya_eslesmez(tmp_path: Path) -> None:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home, "stil", "paths:\n  - '*.css'\n")
    registry = CapabilityRegistry(home, root)

    assert skill_paths.activate_for(registry, root, (tmp_path / "dis.css",)) is None
    assert skill_paths.activate_for(registry, root, (root / "a.css",)) is not None

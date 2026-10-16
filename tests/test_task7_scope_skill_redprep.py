"""Paket 7: mevcut API ile kapsam ve skill çakışması davranış kanıtları."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.errors import PathAccessError
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.team import SubTask, derive_sub_context, schedule_waves
from fusion_cli.tools.capabilities import CapabilityRegistry, map_tools
from fusion_cli.tools.files import writable_path


@pytest.mark.parametrize("alias", ["src/../target", "alias"])
def test_task7_canonical_alias_writers_use_separate_waves(tmp_path: Path, alias: str) -> None:
    """Aynı hedefe farklı yazımla giden iki yazıcı birlikte çalışmamalı."""
    (tmp_path / "target").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "target", target_is_directory=True)
    tasks = [
        SubTask("birinci", write_scope=(str(tmp_path / "target"),)),
        SubTask("ikinci", write_scope=(str(tmp_path / alias),)),
    ]

    assert schedule_waves(tasks) == [[0], [1]]


@pytest.mark.parametrize("child_scope", [("tests",), ("src/ui", "tests"), ("src",)])
def test_task7_child_cannot_expand_parent_scope(
    tmp_path: Path, child_scope: tuple[str, ...]
) -> None:
    """Dar parent alanını child bildirimiyle genişletmek açıkça reddedilmeli."""
    parent = ToolContext(root=tmp_path, write_scope=(tmp_path / "src/ui",))

    with pytest.raises(PathAccessError):
        derive_sub_context(parent, SubTask("dar görev", write_scope=child_scope))


def test_task7_child_can_narrow_parent_scope(tmp_path: Path) -> None:
    """Mevcut doğru daraltma ve araç enforcement davranışını koru."""
    parent = ToolContext(root=tmp_path, write_scope=(tmp_path / "src",))
    child = derive_sub_context(parent, SubTask("arayüz", write_scope=("src/ui",)))

    assert writable_path(child, "src/ui/new.py") == tmp_path / "src/ui/new.py"
    with pytest.raises(PathAccessError):
        writable_path(child, "src/backend/new.py")


def test_task7_write_validator_rejects_retargeted_external_symlink(tmp_path: Path) -> None:
    """Başlangıç sonrası dışarı çevrilen symlink yazma izni olmamalı."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "src").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    alias = root / "alias"
    alias.symlink_to(root / "src", target_is_directory=True)
    context = ToolContext(root=root, write_scope=(root / "src",))
    assert writable_path(context, "alias/new.py") == root / "src/new.py"
    alias.unlink()
    alias.symlink_to(outside, target_is_directory=True)

    with pytest.raises(PathAccessError):
        writable_path(context, "alias/new.py")


class OfflineRegistry(CapabilityRegistry):
    """Yalnız tmp_path kaynakları; gerçek kullanıcı kataloğu okunmaz."""

    def _skill_roots(self) -> tuple[tuple[Path, str], ...]:
        return ((self._home / "skills", "claude"), (self._root / "skills", "proje"))


def test_task7_distinct_skill_contents_keep_distinct_origins(tmp_path: Path) -> None:
    """Farklı içerikli aynı adın kaynağı tek kazanan altında kaybolmamalı."""
    home = tmp_path / "home"
    project = tmp_path / "project"
    paths = (home / "skills/example/SKILL.md", project / "skills/example/SKILL.md")
    for path, body in zip(paths, ("yerel yönerge", "proje yönergesi"), strict=True):
        path.parent.mkdir(parents=True)
        path.write_text(f"---\nname: example\n---\n{body}\n", encoding="utf-8")
    registry = OfflineRegistry(home, project)

    entries = registry.skills()

    assert len(entries) == 2
    assert {entry.path for entry in entries} == set(paths)
    assert {entry.source for entry in entries} == {"claude", "proje"}


def test_task7_unknown_tools_do_not_create_grants() -> None:
    """Legacy boş/yıldız ile yalnız bilinmeyen araç ayrımı korunmalı."""
    assert map_tools(()) is None
    assert map_tools(("*",)) is None
    assert map_tools(("unknown-task7-tool",)) == set()
    assert map_tools(("Read", "unknown-task7-tool")) == {"read_file", "view_file"}


def test_task7_ambiguous_skill_requires_qualified_origin(tmp_path: Path) -> None:
    home, project = tmp_path / "home", tmp_path / "project"
    for root, body in ((home, "a"), (project, "b")):
        path = root / "skills/example/SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(f"---\nname: example\n---\n{body}")
    registry = OfflineRegistry(home, project)
    assert registry.get_skill("example") is None
    entries = registry.skills()
    assert len({entry.qualified_name for entry in entries}) == 2
    assert registry.get_skill(entries[1].qualified_name) == entries[1]

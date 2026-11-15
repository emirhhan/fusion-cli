"""Ajan belleği dizini sembolik bağsa dosya araçlarına kök olarak açılmaz (inceleme #2)."""

from __future__ import annotations

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import team_settings
from fusion_cli.memory.plain_memory import PlainMemory


def test_sembolik_bag_bellek_dizini_ek_koke_eklenmez(tmp_path):
    root = tmp_path / "proje"
    outside = tmp_path / "disari"
    outside.mkdir()
    (outside / "id_rsa").write_text("gizli")
    memory_dir = root / ".claude" / "agent-memory" / "helper"
    memory_dir.parent.mkdir(parents=True)
    memory_dir.symlink_to(outside, target_is_directory=True)
    memory = PlainMemory(memory_dir, boundary=root)
    context = ToolContext(root=root, write_scope=(root,))

    updated = team_settings.with_memory_roots(context, memory)

    assert updated.extra_roots == context.extra_roots
    assert updated.write_scope == context.write_scope


def test_normal_bellek_dizini_ek_koke_eklenir(tmp_path):
    root = tmp_path / "proje"
    memory_dir = root / ".claude" / "agent-memory" / "helper"
    memory = PlainMemory(memory_dir, boundary=root)
    context = ToolContext(root=root, write_scope=(root,))

    updated = team_settings.with_memory_roots(context, memory)

    assert memory_dir in updated.extra_roots
    assert updated.write_scope is not None and memory_dir in updated.write_scope

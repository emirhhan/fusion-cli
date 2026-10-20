"""Diğer araçların bellek dosyalarının okunması."""

from __future__ import annotations

from fusion_cli.history.memory_files import read_external_memory


def test_missing_files_return_empty_text(tmp_path):
    assert read_external_memory(tmp_path, tmp_path / "proje") == ""


def test_claude_memory_is_read(tmp_path):
    root = tmp_path / "proje"
    slug = str(root).replace("/", "-")
    target = tmp_path / ".claude" / "projects" / slug / "memory"
    target.mkdir(parents=True)
    (target / "MEMORY.md").write_text("- kullanıcı Türkçe konuşur", encoding="utf-8")

    output = read_external_memory(tmp_path, root)

    assert "kullanıcı Türkçe konuşur" in output
    assert "claude" in output


def test_hermes_memory_is_read(tmp_path):
    target = tmp_path / ".hermes" / "memories"
    target.mkdir(parents=True)
    (target / "USER.md").write_text("- kullanıcı motosiklet satıyor", encoding="utf-8")

    output = read_external_memory(tmp_path, tmp_path / "proje")

    assert "motosiklet" in output


def test_long_memory_file_is_truncated(tmp_path):
    target = tmp_path / ".hermes" / "memories"
    target.mkdir(parents=True)
    (target / "MEMORY.md").write_text("x" * 20_000, encoding="utf-8")

    output = read_external_memory(tmp_path, tmp_path / "proje")

    assert "kırpıldı" in output


def test_blank_memory_file_is_skipped(tmp_path):
    target = tmp_path / ".hermes" / "memories"
    target.mkdir(parents=True)
    (target / "MEMORY.md").write_text("   \n", encoding="utf-8")

    assert read_external_memory(tmp_path, tmp_path / "proje") == ""


def test_invalid_utf8_memory_does_not_hide_other_sources(tmp_path) -> None:
    claude = tmp_path / ".claude" / "projects" / str(tmp_path / "proje").replace("/", "-")
    claude_memory = claude / "memory"
    claude_memory.mkdir(parents=True)
    (claude_memory / "MEMORY.md").write_bytes(b"\xff\xfe")
    hermes_memory = tmp_path / ".hermes" / "memories"
    hermes_memory.mkdir(parents=True)
    (hermes_memory / "USER.md").write_text("geçerli bellek", encoding="utf-8")

    output = read_external_memory(tmp_path, tmp_path / "proje")

    assert "geçerli bellek" in output


def test_symlinked_memory_is_rejected_without_reading_target(tmp_path) -> None:
    target = tmp_path / "ozel.txt"
    target.write_text("okunmamasi gereken ozel icerik", encoding="utf-8")
    memories = tmp_path / ".hermes" / "memories"
    memories.mkdir(parents=True)
    link = memories / "MEMORY.md"
    link.symlink_to(target)

    output = read_external_memory(tmp_path, tmp_path / "proje")

    assert output == ""
    assert "ozel icerik" not in output

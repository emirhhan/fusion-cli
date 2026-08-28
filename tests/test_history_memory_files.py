"""Diğer araçların bellek dosyalarının okunması."""

from __future__ import annotations

from fusion_cli.history.memory_files import read_external_memory


def test_dosya_yoksa_bos_doner(tmp_path):
    assert read_external_memory(tmp_path, tmp_path / "proje") == ""


def test_claude_bellegi_okunur(tmp_path):
    proje = tmp_path / "proje"
    slug = str(proje).replace("/", "-")
    hedef = tmp_path / ".claude" / "projects" / slug / "memory"
    hedef.mkdir(parents=True)
    (hedef / "MEMORY.md").write_text("- kullanıcı Türkçe konuşur", encoding="utf-8")

    cikti = read_external_memory(tmp_path, proje)

    assert "kullanıcı Türkçe konuşur" in cikti
    assert "claude" in cikti


def test_hermes_bellegi_okunur(tmp_path):
    hedef = tmp_path / ".hermes" / "memories"
    hedef.mkdir(parents=True)
    (hedef / "USER.md").write_text("- kullanıcı motosiklet satıyor", encoding="utf-8")

    cikti = read_external_memory(tmp_path, tmp_path / "proje")

    assert "motosiklet" in cikti


def test_uzun_dosya_kirpilir(tmp_path):
    hedef = tmp_path / ".hermes" / "memories"
    hedef.mkdir(parents=True)
    (hedef / "MEMORY.md").write_text("x" * 20_000, encoding="utf-8")

    cikti = read_external_memory(tmp_path, tmp_path / "proje")

    assert "kırpıldı" in cikti


def test_bos_dosya_atlanir(tmp_path):
    hedef = tmp_path / ".hermes" / "memories"
    hedef.mkdir(parents=True)
    (hedef / "MEMORY.md").write_text("   \n", encoding="utf-8")

    assert read_external_memory(tmp_path, tmp_path / "proje") == ""

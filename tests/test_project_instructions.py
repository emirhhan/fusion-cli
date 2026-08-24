"""Hedef projenin CLAUDE.md/AGENTS.md gibi talimat dosyasını okuma — saf fonksiyon."""

from __future__ import annotations

from fusion_cli.engines.agent.project_instructions import (
    MAX_CHARS,
    read_project_instructions,
)


def test_bulunan_ilk_dosya_okunur(tmp_path):
    (tmp_path / "AGENTS.md").write_text("kural: testsiz kod yok", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "kural: testsiz kod yok" in sonuc
    assert "AGENTS.md" in sonuc


def test_oncelik_claude_md_agents_mdden_once_gelir(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("claude kurali", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("agents kurali", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "claude kurali" in sonuc
    assert "agents kurali" not in sonuc


def test_dosya_yoksa_bos_dondurur(tmp_path):
    assert read_project_instructions(tmp_path) == ""


def test_bos_dosya_atlanip_bir_sonrakine_gecilir(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("   ", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("gercek kural", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "gercek kural" in sonuc


def test_uzun_dosya_kirpilir(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x" * (MAX_CHARS + 500), encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "kırpıldı" in sonuc
    assert len(sonuc) < MAX_CHARS + 500

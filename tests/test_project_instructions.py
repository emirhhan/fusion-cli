"""Hedef projenin CLAUDE.md/AGENTS.md gibi talimat dosyasını okuma — saf fonksiyon."""

from __future__ import annotations

from fusion_cli.engines.agent.project_instructions import (
    MAX_CHARS,
    MAX_LINKED_CHARS,
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


def test_bos_claude_md_de_sayilir_agents_md_okunmaz(tmp_path):
    """Claude Code (#146): CLAUDE.md VARSA (boş olsa da) AGENTS.md okunmaz."""
    (tmp_path / "CLAUDE.md").write_text("   ", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("gercek kural", encoding="utf-8")

    assert "gercek kural" not in read_project_instructions(tmp_path)


def test_uzun_dosya_kirpilmadan_tam_yuklenir(tmp_path):
    """Claude Code (#143): 4 MiB'a kadar dosya bütünüyle yüklenir."""
    (tmp_path / "CLAUDE.md").write_text("x" * 20_000 + "SON", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert sonuc.endswith("SON") and "kırpıldı" not in sonuc


def test_dort_mibden_buyuk_dosya_hic_yuklenmez(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x" * (MAX_CHARS + 1), encoding="utf-8")

    assert read_project_instructions(tmp_path) == ""


def test_bos_projeye_de_gercek_ortam_aktarilir(tmp_path, monkeypatch):
    from fusion_cli.engines.agent import project_instructions as instructions

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    monkeypatch.setattr(
        "shutil.which",
        lambda name, path=None: "/opt/homebrew/bin/godot" if name == "godot" else None,
    )
    result = instructions.read_all_instructions(tmp_path, None)
    assert str(tmp_path.resolve()) in result
    assert "Darwin" in result
    assert "arm64" in result
    assert "göreli" in result
    assert "/opt/homebrew/bin/godot" in result


# --- Markdown bağlantıları (#148) --------------------------------------------- #


def test_markdown_baglantilari_izlenmez(tmp_path):
    """Claude Code yalnız `@yol` importu alır; `[metin](dosya.md)` bağlantısı yüklenmez."""
    (tmp_path / "CLAUDE.md").write_text(
        "Kod yazmadan önce [RULES.md](RULES.md) okunur.", encoding="utf-8"
    )
    (tmp_path / "RULES.md").write_text("çekirdek UI bilmez", encoding="utf-8")

    sonuc = read_project_instructions(tmp_path)

    assert "Kod yazmadan önce" in sonuc
    assert "çekirdek UI bilmez" not in sonuc
    assert MAX_LINKED_CHARS == 0

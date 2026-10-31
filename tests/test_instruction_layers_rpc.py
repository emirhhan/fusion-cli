"""`ayar.talimat` yüklenen talimat katmanlarını ve kırpma ölçümünü döndürür (P-015)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.appserver import instructions, voice


def test_ayar_talimat_katmanlari_ve_notlari_dondurur(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path / "veri")
    home, root = tmp_path / "ev", tmp_path / "proje"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("genel", encoding="utf-8")
    root.mkdir()
    (root / "CLAUDE.md").write_text("proje @../disari.md", encoding="utf-8")
    (tmp_path / "disari.md").write_text("x", encoding="utf-8")

    sonuc = instructions.get_instructions(root, home)

    assert sonuc["ok"] is True
    kaynaklar = [item["kaynak"] for item in sonuc["katmanlar"]]
    assert kaynaklar == ["~/.claude/CLAUDE.md", "CLAUDE.md"]
    assert sonuc["katmanlar"][0]["guvenilir"] is True
    assert sonuc["katmanlar"][1]["guvenilir"] is False
    assert sonuc["toplam_karakter"] == len("genel") + len("proje @../disari.md")
    assert any("disari.md" in not_ for not_ in sonuc["notlar"])


def test_ayar_talimat_kok_verilmezse_eski_yanit(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path / "veri")

    sonuc = instructions.get_instructions()

    assert "katmanlar" not in sonuc and sonuc["ok"] is True


def test_ayar_talimat_kural_dosyalarini_kapsamiyla_listeler(tmp_path: Path, monkeypatch):
    """Eksik yüzey: Kişiselleştirme ekranı `.claude/rules` kurallarını göstermiyordu."""
    monkeypatch.setattr(voice, "_data_home", lambda: tmp_path / "veri")
    home, root = tmp_path / "ev", tmp_path / "proje"
    (root / ".claude" / "rules").mkdir(parents=True)
    (root / ".claude" / "rules" / "react.md").write_text(
        "---\npaths: [src/**/*.tsx]\n---\nhook adı use ile başlar", encoding="utf-8"
    )
    (root / "CLAUDE.md").write_text("proje", encoding="utf-8")

    sonuc = instructions.get_instructions(root, home)

    kural = next(item for item in sonuc["katmanlar"] if item["katman"] == "kural")
    assert kural["kaynak"] == ".claude/rules/react.md"
    assert kural["kapsam"] == ["src/**/*.tsx"]
    assert kural["guvenilir"] is False and kural["karakter"] > 0

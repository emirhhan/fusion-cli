"""`--add-dir` dizininin `paths` alanlı kuralları dosya erişiminde etkinleşir (Claude Code #170)."""

from __future__ import annotations

from pathlib import Path

from fusion_cli.engines.agent import extra_dir_rules


def _ek(tmp_path: Path) -> Path:
    ek = tmp_path / "ek"
    kurallar = ek / ".claude" / "rules"
    kurallar.mkdir(parents=True)
    (kurallar / "tsx.md").write_text("---\npaths: 'src/**/*.tsx'\n---\nKOSULLU KURAL", "utf-8")
    (kurallar / "genel.md").write_text("GENEL", "utf-8")
    return ek


def test_ortam_degiskeni_kapaliyken_yuklenmez(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", raising=False)
    ek = _ek(tmp_path)

    hits = extra_dir_rules.hits_for(
        (ek,), ek / "src" / "a" / "App.tsx", loaded=set(), present=lambda _: False
    )
    assert hits == []


def test_eslesen_erisimde_bir_kez_gelir_olay_path_glob_match(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", "1")
    ek = _ek(tmp_path)
    loaded: set[str] = set()

    assert (
        extra_dir_rules.hits_for((ek,), ek / "README.md", loaded=loaded, present=lambda _: False)
        == []
    )
    hedef = ek / "src" / "a" / "App.tsx"
    hits = extra_dir_rules.hits_for((ek,), hedef, loaded=loaded, present=lambda _: False)
    note = extra_dir_rules.note_for(hits)

    assert len(hits) == 1 and note is not None
    assert "KOSULLU KURAL" in note.content and "GENEL" not in note.content
    assert hits[0].event["load_reason"] == "path_glob_match"
    assert hits[0].event["globs"] == ["src/**/*.tsx"]
    assert hits[0].event["trigger_file_path"] == str(hedef)
    # İkinci erişim tekrar eklemez; ek dizin dışındaki dosya eşleşmez.
    assert extra_dir_rules.hits_for((ek,), hedef, loaded=loaded, present=lambda _: False) == []
    assert (
        extra_dir_rules.hits_for(
            (ek,), tmp_path / "src" / "b.tsx", loaded=set(), present=lambda _: False
        )
        == []
    )


def test_ortam_degiskeni_tek_yerde_ayristirilir(monkeypatch) -> None:
    """#170: talimat katmanları ve koşullu kurallar aynı ayrıştırıcıyı kullanır."""
    from fusion_cli.engines.agent import instruction_layers

    for value, expected in (("1", True), ("true", True), ("TRUE", True), ("0", False), ("", False)):
        monkeypatch.setenv("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", value)
        assert instruction_layers.additional_dirs_enabled() is expected
        assert extra_dir_rules.enabled() is expected


def test_kural_agaci_her_dosya_erisiminde_yeniden_taranmaz(tmp_path: Path, monkeypatch) -> None:
    """#170: aynı ek dizin için ardışık erişimler kural ağacını bir kez tarar."""
    monkeypatch.setenv("CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD", "1")
    ek = _ek(tmp_path)
    calls: list[Path] = []
    real_scan = extra_dir_rules._scan

    def counting(path, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(path)
        return real_scan(path, **kwargs)

    monkeypatch.setattr(extra_dir_rules, "_scan", counting)
    for name in ("a.py", "b.py", "c.py"):
        extra_dir_rules.hits_for((ek,), ek / name, loaded=set(), present=lambda _: False)

    assert len(calls) == 1

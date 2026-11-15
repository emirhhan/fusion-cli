"""İç içe talimat ve `.claude/rules` Claude Code ile birebir (#152, #153, #154, #155, #156)."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.engines.agent import claude_md_imports
from fusion_cli.engines.agent.instruction_rules import discover_rules
from fusion_cli.engines.agent.project_instructions import NESTED_MAX_CHARS, load_nested_instructions


def _yukle(kok: Path, hedef: Path) -> str:
    sonuc = load_nested_instructions(kok, hedef, loaded=set(), present=lambda rel: False)
    return sonuc.message.content if sonuc is not None else ""


def test_alt_dizinde_claude_ve_local_birlikte_agents_yalniz_yoksa(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "CLAUDE.md").write_text("A-CLAUDE", "utf-8")
    (tmp_path / "a" / "CLAUDE.local.md").write_text("A-YEREL", "utf-8")
    (tmp_path / "a" / "AGENTS.md").write_text("A-AJAN", "utf-8")
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "AGENTS.md").write_text("B-AJAN", "utf-8")
    (tmp_path / "b" / "GEMINI.md").write_text("B-GEMINI", "utf-8")
    for klasor in ("a", "b"):
        (tmp_path / klasor / "x.py").write_text("pass", "utf-8")

    a = _yukle(tmp_path, tmp_path / "a" / "x.py")
    b = _yukle(tmp_path, tmp_path / "b" / "x.py")

    assert "A-CLAUDE" in a and "A-YEREL" in a and "A-AJAN" not in a
    assert "B-AJAN" in b and "B-GEMINI" not in b
    assert NESTED_MAX_CHARS == 40_000


def test_mdc_ve_globs_okunmaz(tmp_path: Path) -> None:
    kurallar = tmp_path / ".claude" / "rules"
    kurallar.mkdir(parents=True)
    (kurallar / "a.mdc").write_text("cursor", "utf-8")
    (kurallar / "b.md").write_text("---\nglobs: ['*.py']\n---\nb", "utf-8")

    bulunan = discover_rules(tmp_path, None)

    assert [k.label for k in bulunan] == [".claude/rules/b.md"]
    assert bulunan[0].paths == ()


def test_kok_disi_kural_bagi_onaydan_sonra_yuklenir(tmp_path: Path) -> None:
    ortak = tmp_path / "ortak.md"
    ortak.write_text("ORTAK", "utf-8")
    proje = tmp_path / "p"
    (proje / ".claude" / "rules").mkdir(parents=True)
    (proje / ".claude" / "rules" / "ortak.md").symlink_to(ortak)

    assert discover_rules(proje, None) == ()
    claude_md_imports.set_external_import_decision(proje, True)
    assert [k.label for k in discover_rules(proje, None)] == [".claude/rules/ortak.md"]


def test_claude_md_excludes_kurallara_da_uygulanir(tmp_path: Path) -> None:
    kurallar = tmp_path / ".claude" / "rules"
    kurallar.mkdir(parents=True)
    (kurallar / "baska.md").write_text("x", "utf-8")
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"claudeMdExcludes": ["**/rules/baska.md"]}), "utf-8"
    )

    assert discover_rules(tmp_path, None) == ()

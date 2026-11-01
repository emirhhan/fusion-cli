"""`/doctor prompt-audit [yol]`: talimat dosyalarının model denetimi (Claude Code #168)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import Engine, ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.engines.agent.prompt_audit import audit_scope, prompt_audit_task
from fusion_cli.memory.factory import null_memory


@pytest.fixture
def dizinler(tmp_path: Path) -> tuple[Path, Path]:
    home, root = tmp_path / "ev", tmp_path / "proje"
    (root / ".claude" / "rules").mkdir(parents=True)
    (root / ".claude" / "skills" / "inceleme").mkdir(parents=True)
    (root / "paket" / "node_modules" / "x").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("`make test` koş", "utf-8")
    (root / ".claude" / "rules" / "stil.md").write_text("kural", "utf-8")
    (root / ".claude" / "skills" / "inceleme" / "SKILL.md").write_text("---\n---\n", "utf-8")
    (root / "paket" / "AGENTS.md").write_text("alt", "utf-8")
    (root / "paket" / "node_modules" / "x" / "CLAUDE.md").write_text("üçüncü", "utf-8")
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("kişisel", "utf-8")
    return home, root


def test_kapsam_katmanlari_ve_yol_daraltmasi(dizinler: tuple[Path, Path]) -> None:
    home, root = dizinler
    names = {p.relative_to(p.parents[1]).as_posix() for p in audit_scope(root, home)}
    assert {"proje/CLAUDE.md", "rules/stil.md", "inceleme/SKILL.md", "paket/AGENTS.md"} <= names
    assert not any("node_modules" in str(p) for p in audit_scope(root, home))
    assert any(str(p).endswith("ev/.claude/CLAUDE.md") for p in audit_scope(root, home))

    assert audit_scope(root, home, "paket") == ((root / "paket" / "AGENTS.md").resolve(),)
    assert audit_scope(root, home, "yok") == ()


def test_gorev_dosyalari_listeler_ve_onaysiz_degistirmez(dizinler: tuple[Path, Path]) -> None:
    home, root = dizinler
    task = prompt_audit_task(root, home, findings="ön bulgu")

    assert "`CLAUDE.md`" in task and "`~/.claude/CLAUDE.md`" in task
    assert "`.claude/rules/stil.md`" in task and "ön bulgu" in task
    assert "DEĞİŞTİRME" in task and "onay" in task
    assert prompt_audit_task(root, home, "yok") == ""


def test_doctor_prompt_audit_turu_hazirlar_motoru_degistirmez(
    dizinler: tuple[Path, Path], tmp_path: Path
) -> None:
    home, root = dizinler
    source = tmp_path / "config.yaml"
    source.write_text("", encoding="utf-8")
    state = ReplState(config=load_config(source), memory=null_memory(), root=root, home=home)
    oturum_motoru = state.engine
    doctor = build_registry(home).get("doctor")
    assert doctor is not None

    cikti = doctor.handler(state, "prompt-audit .claude/rules")
    gorev, _ = state.take_pending()

    assert "prompt-audit" in cikti
    assert "`.claude/rules/stil.md`" in gorev and "`CLAUDE.md`" not in gorev
    assert state.engine is oturum_motoru and state.take_turn_engine() is Engine.AGENT
    assert "bulunamadı" in doctor.handler(state, "prompt-audit yok/yol")

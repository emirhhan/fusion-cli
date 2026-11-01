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


def test_ic_ice_tarama_derinlik_ve_dizin_sinirli(tmp_path, monkeypatch) -> None:
    """#168: yolsuz denetim ev dizini gibi büyük köklerde sınırsız gezmez."""
    from fusion_cli.engines.agent import prompt_audit

    deep = tmp_path
    for index in range(prompt_audit.MAX_WALK_DEPTH + 3):
        deep = deep / f"d{index}"
    deep.mkdir(parents=True)
    (deep / "CLAUDE.md").write_text("derin", encoding="utf-8")
    shallow = tmp_path / "d0" / "CLAUDE.md"
    shallow.write_text("sığ", encoding="utf-8")

    found = prompt_audit.audit_scope(tmp_path, None)
    assert shallow in found and deep / "CLAUDE.md" not in found

    for index in range(10):
        (tmp_path / f"genis{index}").mkdir()
    monkeypatch.setattr(prompt_audit, "MAX_WALK_DIRS", 3)
    visited: list[str] = []
    real_walk = prompt_audit.os.walk

    def counting_walk(*args, **kwargs):  # type: ignore[no-untyped-def]
        for item in real_walk(*args, **kwargs):
            visited.append(item[0])
            yield item

    monkeypatch.setattr(prompt_audit.os, "walk", counting_walk)
    prompt_audit.audit_scope(tmp_path, None)
    assert len(visited) <= 4


def test_dis_hedefe_isaret_eden_bag_kendi_yoluyla_listelenir(tmp_path) -> None:
    """#168: kök içindeki sembolik bağ, kök dışındaki gerçek yolla listelenmez."""
    from fusion_cli.engines.agent import prompt_audit

    outside = tmp_path / "dis" / "CLAUDE.md"
    outside.parent.mkdir()
    outside.write_text("dış", encoding="utf-8")
    root = tmp_path / "proje"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "CLAUDE.md").symlink_to(outside)

    found = prompt_audit.audit_scope(root, None)

    assert root.resolve() / "pkg" / "CLAUDE.md" in found
    assert outside.resolve() not in found

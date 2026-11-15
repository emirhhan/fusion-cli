"""Otomatik bellek Claude Code konumunda (#153).

Belge (memory, "Auto memory"): `~/.claude/projects/<project>/memory/MEMORY.md`; `<project>` git
deposundan türer (worktree'ler ve alt dizinler paylaşır); `autoMemoryEnabled`,
`autoMemoryDirectory`, `CLAUDE_CODE_DISABLE_AUTO_MEMORY`.
"""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.memory import auto_memory_location as location
from fusion_cli.memory.plain_memory import build_plain_memory, legacy_project_memory_dir

from .fakes import make_config


def _depo(tmp_path: Path) -> Path:
    depo = tmp_path / "depo"
    (depo / ".git").mkdir(parents=True)
    (depo / "paket" / "alt").mkdir(parents=True)
    return depo


def test_bellek_claude_projects_altinda_git_kokunden_turer(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    config = make_config()

    memory = build_plain_memory(config, depo / "paket" / "alt")

    assert memory is not None
    assert memory.index_path.name == "MEMORY.md"
    beklenen = location.claude_home() / ".claude" / "projects" / location.project_key(depo)
    assert memory.directory == beklenen / "memory"
    assert build_plain_memory(config, depo).directory == memory.directory  # type: ignore[union-attr]


def test_worktree_ana_depoyla_ayni_bellegi_paylasir(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    (depo / ".git" / "worktrees" / "wt").mkdir(parents=True)
    agac = tmp_path / "agac"
    agac.mkdir()
    (agac / ".git").write_text(f"gitdir: {depo / '.git' / 'worktrees' / 'wt'}\n", encoding="utf-8")

    assert location.repository_root(agac) == depo.resolve()


def test_ortam_degiskeni_ve_ayar_kapatir(tmp_path: Path, monkeypatch) -> None:
    depo = _depo(tmp_path)
    config = make_config()
    monkeypatch.setenv("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "1")
    assert build_plain_memory(config, depo) is None
    monkeypatch.delenv("CLAUDE_CODE_DISABLE_AUTO_MEMORY")

    (depo / ".claude").mkdir()
    (depo / ".claude" / "settings.json").write_text(
        json.dumps({"autoMemoryEnabled": False}), encoding="utf-8"
    )
    assert build_plain_memory(config, depo) is None


def test_auto_memory_directory_proje_katmanindan_kabul_edilmez(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    (depo / ".claude").mkdir()
    (depo / ".claude" / "settings.json").write_text(
        json.dumps({"autoMemoryDirectory": str(tmp_path / "proje-yonlendirme")}), encoding="utf-8"
    )
    (depo / ".claude" / "settings.local.json").write_text(
        json.dumps({"autoMemoryDirectory": str(tmp_path / "yerel")}), encoding="utf-8"
    )

    memory = build_plain_memory(make_config(), depo)

    assert memory is not None and memory.directory == tmp_path / "yerel"


def test_eski_fusion_bellegi_bir_kez_tasinir(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    config = make_config()
    eski = legacy_project_memory_dir(config, depo)
    eski.mkdir(parents=True)
    (eski / "BELLEK.md").write_text("- eski not\n", encoding="utf-8")

    memory = build_plain_memory(config, depo)

    assert memory is not None and "eski not" in memory.read()
    assert (eski / "BELLEK.md").is_file()

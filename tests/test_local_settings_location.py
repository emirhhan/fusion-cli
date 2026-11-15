"""`.claude/settings.local.json` git deposunun kökünde (worktree'de ana checkout) — #67, #68.

Claude: "saves the rule to .claude/settings.local.json at the root of the git repository,
resolved through worktrees to the main checkout"; alt dizinde başlatılsa da kökteki dosya
okunur. Depo dışında oturum kökü kullanılır.
"""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.config import permission_admin, trust
from fusion_cli.config.local_settings_location import local_settings_path
from fusion_cli.config.permission_rules import (
    LAYER_LOCAL,
    PermissionDecision,
    PermissionRule,
    rule_layers,
)

LOCAL = Path(".claude") / "settings.local.json"


def _worktree(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "ana"
    (main / ".git" / "worktrees" / "dal").mkdir(parents=True)
    gitdir = main / ".git" / "worktrees" / "dal"
    (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    worktree = tmp_path / "dal"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    return main, worktree


def test_depo_disinda_oturum_koku_kullanilir(tmp_path):
    assert local_settings_path(tmp_path) == tmp_path / LOCAL


def test_alt_dizinde_git_kokundeki_dosya(tmp_path):
    (tmp_path / ".git").mkdir()
    sub = tmp_path / "paket" / "alt"
    sub.mkdir(parents=True)
    assert local_settings_path(sub) == tmp_path.resolve() / LOCAL


def test_worktreede_ana_checkout_kokundeki_dosya(tmp_path):
    main, worktree = _worktree(tmp_path)
    assert local_settings_path(worktree) == main.resolve() / LOCAL
    assert local_settings_path(worktree / "src") == main.resolve() / LOCAL


def test_alt_modulde_commondir_yoksa_modul_koku(tmp_path):
    gitdir = tmp_path / "ust" / ".git" / "modules" / "m"
    gitdir.mkdir(parents=True)
    module = tmp_path / "ust" / "m"
    module.mkdir()
    (module / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    assert local_settings_path(module) == module.resolve() / LOCAL


def test_bozuk_git_dosyasinda_depo_koku(tmp_path):
    (tmp_path / ".git").write_text("bozuk", encoding="utf-8")
    assert local_settings_path(tmp_path) == tmp_path.resolve() / LOCAL


def test_yerel_katman_ana_checkouttan_okunur(tmp_path):
    main, worktree = _worktree(tmp_path)
    layer = next(item for item in rule_layers(worktree) if item.name == LAYER_LOCAL)
    assert layer.path == main.resolve() / LOCAL


def test_bir_daha_sorma_ana_checkouta_yazar(tmp_path):
    main, worktree = _worktree(tmp_path)
    rule = PermissionRule("Bash", "npm test *", PermissionDecision.ALLOW)
    change = permission_admin.add_permission_rule(worktree, rule)
    assert change.path == main.resolve() / LOCAL
    assert not change.fell_back
    data = json.loads((main / LOCAL).read_text(encoding="utf-8"))
    assert data["permissions"]["allow"] == ["Bash(npm test *)"]
    assert not (worktree / LOCAL).exists()
    # Fusion'ın yazdığı dosya bir sonraki turda güvenilmiyor diye düşmez.
    assert trust.is_permissions_trusted(worktree)

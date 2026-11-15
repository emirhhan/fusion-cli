"""Tek değer okuyucuları da managed katmanı en üstte görür (bağımsız inceleme #3).

Claude Code (settings#settings-precedence): managed > komut satırı > yerel > proje > kullanıcı.
`plansDirectory`, `bashOutputMaxChars`, `worktree.baseRef`, `worktree.symlinkDirectories`
aynı sırayla okunur.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

import pytest

from fusion_cli.config import claude_settings, claude_top_layers
from fusion_cli.config.claude_settings import claude_setting
from fusion_cli.config.worktree_settings import worktree_base_mode, worktree_layout


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    managed = tmp_path / "managed"
    managed.mkdir()
    monkeypatch.setattr(claude_top_layers, "MANAGED_DIRS", {platform.system(): managed})
    for modul in (claude_settings,):
        monkeypatch.setattr(modul, "is_project_settings_trusted", lambda _root: True)
        monkeypatch.setattr(modul, "is_permissions_trusted", lambda _root: True)
    root, home = tmp_path / "proje", tmp_path / "ev"
    root.mkdir()
    home.mkdir()
    return root, home, managed


def _yaz(path: Path, veri: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(veri), encoding="utf-8")


def test_claude_setting_managed_yerel_dosyayi_ezer(ortam):
    root, home, managed = ortam
    _yaz(root / ".claude" / "settings.local.json", {"plansDirectory": "yerel"})
    assert claude_setting(root, "plansDirectory", home=home) == "yerel"
    _yaz(managed / "managed-settings.json", {"plansDirectory": "/sirket/planlar"})
    assert claude_setting(root, "plansDirectory", home=home) == "/sirket/planlar"


def test_worktree_base_ref_managed_kazanir(ortam):
    root, home, managed = ortam
    _yaz(home / ".claude" / "settings.json", {"worktree": {"baseRef": "fresh"}})
    _yaz(managed / "managed-settings.d" / "10.json", {"worktree": {"baseRef": "head"}})
    assert worktree_base_mode(root, home=home) == "head"


def test_worktree_layout_managed_listesi_birlesir(ortam):
    root, home, managed = ortam
    _yaz(root / ".claude" / "settings.json", {"worktree": {"symlinkDirectories": ["a"]}})
    _yaz(managed / "managed-settings.json", {"worktree": {"symlinkDirectories": ["b"]}})
    assert worktree_layout(root, home=home).symlink_dirs == ("a", "b")

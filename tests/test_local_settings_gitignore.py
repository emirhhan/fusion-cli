"""İlk "bir daha sorma" yazımında yerel dosya genel git dışlamasına eklenir (Claude, #67).

Claude: "When Claude Code first writes .claude/settings.local.json in a git repo that doesn't
already ignore it, it adds the file to your global git excludes". Elle oluşturulan dosyaya
dokunulmaz; depo dışında hiçbir şey yazılmaz.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fusion_cli.config import permission_admin
from fusion_cli.config.local_settings_gitignore import IGNORE_LINE, global_excludes_file
from fusion_cli.config.permission_rules import PermissionDecision, PermissionRule

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git yok")

RULE = PermissionRule("Bash", "npm test *", PermissionDecision.ALLOW)


@pytest.fixture
def depo(tmp_path, monkeypatch) -> Path:
    # Gerçek ~/.gitconfig ve sistem ayarı okunmasın.
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    root = tmp_path / "depo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def _ignored(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "-q", ".claude/settings.local.json"],
        check=False,
    )
    return result.returncode == 0


def test_ilk_yazimda_genel_dislamaya_eklenir(depo, tmp_path):
    permission_admin.add_permission_rule(depo, RULE)
    excludes = tmp_path / "xdg" / "git" / "ignore"
    assert IGNORE_LINE in excludes.read_text(encoding="utf-8").splitlines()
    assert _ignored(depo)


def test_core_excludesfile_varsa_oraya_yazilir(depo, tmp_path):
    custom = tmp_path / "ozel-ignore"
    custom.write_text("*.log\n", encoding="utf-8")
    subprocess.run(
        ["git", "config", "--global", "core.excludesFile", str(custom)], check=True, cwd=depo
    )
    assert global_excludes_file(depo) == custom
    permission_admin.add_permission_rule(depo, RULE)
    assert custom.read_text(encoding="utf-8").splitlines() == ["*.log", IGNORE_LINE]


def test_zaten_dislaniyorsa_dokunulmaz(depo, tmp_path):
    (depo / ".gitignore").write_text(".claude/\n", encoding="utf-8")
    permission_admin.add_permission_rule(depo, RULE)
    assert not (tmp_path / "xdg" / "git" / "ignore").exists()


def test_elle_olusturulan_dosyada_dokunulmaz(depo, tmp_path):
    (depo / ".claude").mkdir()
    (depo / ".claude" / "settings.local.json").write_text("{}", encoding="utf-8")
    permission_admin.add_permission_rule(depo, RULE)
    assert not (tmp_path / "xdg" / "git" / "ignore").exists()


def test_depo_disinda_dislama_yazilmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    root = tmp_path / "duz"
    root.mkdir()
    permission_admin.add_permission_rule(root, RULE)
    assert not (tmp_path / "xdg" / "git").exists()


def test_git_yoksa_kural_yine_yazilir(depo, monkeypatch, tmp_path):
    monkeypatch.setenv("PATH", str(tmp_path / "bos"))
    change = permission_admin.add_permission_rule(depo, RULE)
    assert change.changed and change.path.is_file()
    assert os.environ["PATH"].endswith("bos")

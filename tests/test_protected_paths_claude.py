"""Korumalı yollar Claude Code listesiyle birebir (#69).

Kaynak: https://code.claude.com/docs/en/permission-modes#protected-paths
"""

from __future__ import annotations

import pytest

from fusion_cli.tools.protected_paths import protected_path_reason


@pytest.mark.parametrize(
    "yol",
    [
        ".git/config",
        ".config/git/config",
        ".vscode/settings.json",
        ".idea/x.xml",
        ".husky/pre-commit",
        ".cargo/config.toml",
        ".devcontainer/devcontainer.json",
        ".yarn/x",
        ".mvn/wrapper/x",
        ".claude/settings.json",
        "alt/.git/HEAD",
        ".gitconfig",
        ".gitmodules",
        ".zshrc",
        ".npmrc",
        "pkg/.npmrc",
        ".pre-commit-config.yaml",
        "lefthook.yml",
        ".mcp.json",
        ".claude.json",
        "gradle/wrapper/gradle-wrapper.properties",
    ],
)
def test_claude_korumali_yollari(tmp_path, yol):
    assert protected_path_reason("write_file", {"path": yol}, tmp_path) is not None


@pytest.mark.parametrize(
    "yol",
    [
        ".claude/worktrees/is/a.py",
        ".claude/agent-memory/x/notlar.md",
        ".github/workflows/ci.yml",
        "src/app.py",
        "zshrc.txt",
    ],
)
def test_istisnalar_ve_listede_olmayanlar(tmp_path, yol):
    assert protected_path_reason("write_file", {"path": yol}, tmp_path) is None


def test_ev_dizinindeki_kabuk_rc_dosyasi_korunur(tmp_path):
    ev_rc = tmp_path.parent / "ev" / ".bashrc"
    assert protected_path_reason("write_file", {"path": str(ev_rc)}, tmp_path) is not None
    komut = {"command": f"echo x >> {ev_rc}"}
    assert protected_path_reason("run_shell", komut, tmp_path, is_shell=True) is not None

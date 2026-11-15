"""Eklenti `bin/` klasörü run_shell PATH'ine (Claude Code plugins-reference "bin/", #389)."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fusion_cli.config.plugin_bin import plugin_bin_dirs, with_plugin_bin
from fusion_cli.tools import plugin_install


def _plugin(folder: Path, name: str, *, with_bin: bool = True) -> Path:
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}), "utf-8")
    (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: A\n---\nA\n", "utf-8")
    if with_bin:
        (folder / "bin").mkdir()
        tool = folder / "bin" / f"{name}-arac"
        tool.write_text("#!/bin/sh\necho merhaba\n", "utf-8")
        tool.chmod(0o755)
    return folder


def test_etkin_eklentinin_bin_klasoru_path_sonuna_eklenir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    plugin_install.install_plugin(str(_plugin(tmp_path / "a", "araci")), approve=lambda _p: True)
    plugin_install.install_plugin(
        str(_plugin(tmp_path / "b", "binsiz", with_bin=False)), approve=lambda _p: True
    )

    dirs = plugin_bin_dirs(tmp_path)
    assert [d.parent.name for d in dirs] == ["araci"]
    env = with_plugin_bin({"PATH": "/usr/bin"}, tmp_path)
    assert env["PATH"].split(os.pathsep) == ["/usr/bin", str(dirs[0])]

    plugin_install.set_plugin_enabled("araci", False)
    assert with_plugin_bin({"PATH": "/usr/bin"}, tmp_path) == {"PATH": "/usr/bin"}


def test_run_shell_ortami_eklenti_bin_klasorunu_gorur(tmp_path, monkeypatch):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.tools.shell import _shell_env

    monkeypatch.chdir(tmp_path)
    plugin_install.install_plugin(str(_plugin(tmp_path / "a", "araci")), approve=lambda _p: True)
    env = _shell_env(ToolContext(root=tmp_path))
    assert env["PATH"].endswith(str(plugin_bin_dirs(tmp_path)[0]))

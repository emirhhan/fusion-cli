"""`/terminal-setup` (#227)."""

from __future__ import annotations

import json
from pathlib import Path

from fusion_cli.cli.repl import terminal_setup as ts
from fusion_cli.cli.repl.commands import build_registry


def test_terminal_tanima():
    assert ts.detect({"TERM_PROGRAM": "vscode"}) == "vscode"
    assert ts.detect({"TERM_PROGRAM": "vscode", "CURSOR_TRACE_ID": "x"}) == "cursor"
    assert ts.detect({"TERM_PROGRAM": "zed"}) == "zed"
    assert ts.detect({"TERM_PROGRAM": "Apple_Terminal"}) == "apple"
    assert ts.detect({"LC_TERMINAL": "iTerm2"}) == "iterm"
    assert ts.detect({"TERM": "alacritty"}) == "alacritty"
    assert ts.detect({}) is None


def test_vscode_bag_kurulur_ikinci_kez_dokunulmaz(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ts.sys, "platform", "linux")
    out = ts.terminal_setup(tmp_path, {"TERM_PROGRAM": "vscode"})
    user = tmp_path / ".config" / "Code" / "User"
    bindings = json.loads((user / "keybindings.json").read_text(encoding="utf-8"))
    assert "Installed VSCode terminal Shift+Enter" in out
    assert bindings[0]["args"]["text"] == "\u001b\r" and bindings[0]["when"] == "terminalFocus"
    settings = json.loads((user / "settings.json").read_text(encoding="utf-8"))
    assert settings["terminal.integrated.gpuAcceleration"] == "off"
    assert "already configured" in ts.terminal_setup(tmp_path, {"TERM_PROGRAM": "vscode"})
    assert len(json.loads((user / "keybindings.json").read_text(encoding="utf-8"))) == 1


def test_vscode_yorumlu_dosya_degistirilmez(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(ts.sys, "platform", "linux")
    user = tmp_path / ".config" / "Code" / "User"
    user.mkdir(parents=True)
    (user / "keybindings.json").write_text("// yorum\n[]", encoding="utf-8")
    out = ts.terminal_setup(tmp_path, {"TERM_PROGRAM": "vscode"})
    assert "kendiniz ekleyin" in out
    assert (user / "keybindings.json").read_text(encoding="utf-8") == "// yorum\n[]"


def test_zed_yedekler_ve_birlestirir(tmp_path: Path):
    keymap = tmp_path / ".config" / "zed" / "keymap.json"
    keymap.parent.mkdir(parents=True)
    keymap.write_text(json.dumps([{"context": "Editor", "bindings": {"x": "y"}}]), "utf-8")
    assert "Installed Zed" in ts.terminal_setup(tmp_path, {"TERM_PROGRAM": "zed"})
    merged = json.loads(keymap.read_text(encoding="utf-8"))
    assert merged[0]["context"] == "Editor" and merged[1]["context"] == "Terminal"
    assert list(keymap.parent.glob("keymap.json.*.bak"))


def test_alacritty_ve_apple_ve_iterm(tmp_path: Path):
    assert "Installed Alacritty" in ts.terminal_setup(tmp_path, {"TERM": "alacritty"})
    assert "already" in ts.terminal_setup(tmp_path, {"TERM": "alacritty"})
    komutlar: list[list[str]] = []

    def run(command: list[str]) -> tuple[int, str]:
        komutlar.append(command)
        return (0, "Basic") if command[1] == "read" else (0, "")

    out = ts.terminal_setup(tmp_path, {"TERM_PROGRAM": "Apple_Terminal"}, run)
    assert "Basic" in out and any("useOptionAsMetaKey" in " ".join(c) for c in komutlar)
    assert any("Bell" in " ".join(c) for c in komutlar)
    out = ts.terminal_setup(tmp_path, {"TERM_PROGRAM": "iTerm.app"}, run)
    assert "pano" in out and komutlar[-1][-3:] == ["AllowClipboardAccess", "-bool", "true"]


def test_komut_kayitli():
    assert build_registry().get("terminal-setup") is not None

"""`/terminal-setup` (#227) — Claude Code ile aynı terminal ayarları.

- VS Code, Cursor, Devin Desktop: kullanıcı `keybindings.json`'una Shift+Enter → ESC CR
  (`workbench.action.terminal.sendSequence`, `terminalFocus`) bağı; `settings.json`'da
  `terminal.integrated.gpuAcceleration: "off"`.
- Zed: `keymap.json`'a Terminal bağlamında `shift-enter` → `terminal::SendText`; mevcut
  dosya önce `keymap.json.<karma>.bak` olarak yedeklenir. Okunamayan dosya değiştirilmez,
  eklenecek blok yazdırılır.
- Alacritty: `alacritty.toml`'a Shift+Return → ESC CR bağı eklenir.
- Apple Terminal: varsayılan profilde "Use Option as Meta Key" açılır, sesli zil kapanır.
- iTerm2: "Applications in terminal may access clipboard" açılır (`/copy` için).

Var olan bağ yerinde bırakılır ("zaten kurulu"). Fusion'ın TUI'si ESC CR'yi (Option+Enter)
yeni satır olarak okur (#197), bu yüzden bütün bağlar aynı diziyi gönderir.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

NEWLINE_SEQUENCE = "\u001b\r"
Runner = Callable[[list[str]], tuple[int, str]]

_VSCODE_BINDING = {
    "key": "shift+enter",
    "command": "workbench.action.terminal.sendSequence",
    "args": {"text": NEWLINE_SEQUENCE},
    "when": "terminalFocus",
}
_ZED_BLOCK = {
    "context": "Terminal",
    "bindings": {"shift-enter": ["terminal::SendText", "\u001b\r"]},
}
_ALACRITTY_BLOCK = '\n[[keyboard.bindings]]\nkey = "Return"\nmods = "Shift"\nchars = "\\u001b\\r"\n'
_EDITOR_DIRS = {"vscode": "Code", "cursor": "Cursor", "devin": "Devin"}


def detect(env: Mapping[str, str]) -> str | None:
    """Ortamdan terminali tanı; bilinmiyorsa None."""
    program = env.get("TERM_PROGRAM", "")
    if program == "vscode":
        hints = " ".join(
            env.get(k, "") for k in ("VSCODE_GIT_ASKPASS_NODE", "__CFBundleIdentifier")
        )
        if env.get("CURSOR_TRACE_ID") or "cursor" in hints.lower():
            return "cursor"
        return "devin" if "devin" in hints.lower() else "vscode"
    if program == "zed":
        return "zed"
    if program == "Apple_Terminal":
        return "apple"
    if program == "iTerm.app" or env.get("LC_TERMINAL") == "iTerm2":
        return "iterm"
    if env.get("TERM") == "alacritty" or env.get("ALACRITTY_WINDOW_ID"):
        return "alacritty"
    return None


def _editor_user_dir(home: Path, app: str) -> Path:
    current: str = sys.platform  # testte değiştirilir; mypy platform daraltması yapmasın
    if current == "darwin":
        return home / "Library" / "Application Support" / app / "User"
    return home / ".config" / app / "User"


def _read_json_list(path: Path) -> list[object] | None:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
    except (OSError, ValueError):
        return None
    return data if isinstance(data, list) else None


def setup_vscode(home: Path, kind: str) -> list[str]:
    name = {"vscode": "VSCode", "cursor": "Cursor", "devin": "Devin Desktop"}[kind]
    user_dir = _editor_user_dir(home, _EDITOR_DIRS[kind])
    target = user_dir / "keybindings.json"
    bindings = _read_json_list(target)
    if bindings is None:
        block = json.dumps(_VSCODE_BINDING, indent=2)
        return [f"{target} okunamadı (yorum ya da bozuk JSON); şu bağı kendiniz ekleyin:\n{block}"]
    lines: list[str] = []
    exists = any(
        isinstance(item, dict) and item.get("key") == "shift+enter" and "terminal" in str(item)
        for item in bindings
    )
    if exists:
        lines.append(f"{name} terminal Shift+Enter key binding already configured")
    else:
        user_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps([*bindings, _VSCODE_BINDING], indent=2) + "\n", "utf-8")
        lines.append(f"Installed {name} terminal Shift+Enter key binding ({target})")
    lines.extend(_vscode_settings(user_dir / "settings.json"))
    return lines


def _vscode_settings(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return [f"{path} okunamadı; terminal.integrated.gpuAcceleration ayarı değiştirilmedi"]
    if not isinstance(data, dict) or data.get("terminal.integrated.gpuAcceleration") == "off":
        return []
    updated = {**data, "terminal.integrated.gpuAcceleration": "off"}
    path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return [f'terminal.integrated.gpuAcceleration "off" yapıldı ({path})']


def setup_zed(home: Path) -> list[str]:
    target = home / ".config" / "zed" / "keymap.json"
    block = json.dumps(_ZED_BLOCK, indent=2)
    bindings = _read_json_list(target)
    if bindings is None:
        return [f"{target} değiştirilmedi (okunamadı); şu bloğu kendiniz ekleyin:\n{block}"]
    if any(
        isinstance(item, dict)
        and "shift-enter" in str(item.get("bindings", {}))
        and item.get("context") == "Terminal"
        for item in bindings
    ):
        return ["Zed terminal Shift+Enter key binding already configured"]
    if target.exists() and bindings:
        digest = hashlib.sha256(target.read_bytes()).hexdigest()[:8]
        target.with_name(f"keymap.json.{digest}.bak").write_bytes(target.read_bytes())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps([*bindings, _ZED_BLOCK], indent=2) + "\n", encoding="utf-8")
    return [f"Installed Zed terminal Shift+Enter key binding ({target})"]


def setup_alacritty(home: Path) -> list[str]:
    target = home / ".config" / "alacritty" / "alacritty.toml"
    try:
        text = target.read_text(encoding="utf-8") if target.exists() else ""
    except OSError as error:
        return [f"{target} okunamadı: {error}"]
    if 'mods = "Shift"' in text and "\\u001b\\r" in text:
        return ["Alacritty Shift+Enter key binding already configured"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text + _ALACRITTY_BLOCK, encoding="utf-8")
    return [f"Installed Alacritty Shift+Enter key binding ({target})"]


def _run(command: list[str]) -> tuple[int, str]:  # pragma: no cover - gerçek macOS
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    return result.returncode, (result.stdout or result.stderr).strip()


def setup_apple(home: Path, run: Runner) -> list[str]:
    code, profile = run(["defaults", "read", "com.apple.Terminal", "Default Window Settings"])
    if code != 0 or not profile:
        return [
            "Apple Terminal varsayılan profili okunamadı; Ayarlar › Profiller › Klavye'den "
            '"Use Option as Meta Key" seçin'
        ]
    plist = str(home / "Library" / "Preferences" / "com.apple.Terminal.plist")
    for key, value in (("useOptionAsMetaKey", "true"), ("Bell", "false")):
        entry = f":Window Settings:{profile}:{key}"
        if run(["/usr/libexec/PlistBuddy", "-c", f"Set '{entry}' {value}", plist])[0] != 0:
            run(["/usr/libexec/PlistBuddy", "-c", f"Add '{entry}' bool {value}", plist])
    return [
        f"Apple Terminal '{profile}' profilinde Option as Meta açıldı, sesli zil kapatıldı "
        "(Terminal'i yeniden açın)"
    ]


def setup_iterm(run: Runner) -> list[str]:
    command = [
        "defaults",
        "write",
        "com.googlecode.iterm2",
        "AllowClipboardAccess",
        "-bool",
        "true",
    ]
    if run(command)[0] != 0:
        return ["iTerm2 pano erişimi açılamadı; Settings › General › Selection'dan açın"]
    return [
        "iTerm2'de uygulamaların panoya erişimi açıldı (/copy için); iTerm2'yi yeniden başlatın"
    ]


def terminal_setup(home: Path, env: Mapping[str, str] | None = None, run: Runner = _run) -> str:
    kind = detect(os.environ if env is None else env)
    if kind in _EDITOR_DIRS:
        lines = setup_vscode(home, kind)
    elif kind == "zed":
        lines = setup_zed(home)
    elif kind == "alacritty":
        lines = setup_alacritty(home)
    elif kind == "apple":
        lines = setup_apple(home, run)
    elif kind == "iterm":
        lines = setup_iterm(run)
    else:
        lines = [
            "Bu terminal için kurulum gerekmiyor ya da desteklenmiyor; yeni satır için "
            "Ctrl+J ya da \\ ardından Enter kullanın."
        ]
    return "\n".join(lines)

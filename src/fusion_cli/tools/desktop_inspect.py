"""macOS pencereleri ve erişilebilirlik öğelerini okuyan tamamlayıcı araçlar."""

from __future__ import annotations

import subprocess

from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .desktop import ACCESSIBILITY_ERROR, DESKTOP_COMMAND_TIMEOUT_S, _framework, _mac_only, _trusted

WINDOW_SCRIPT = """
tell application "System Events"
    set output to ""
    repeat with proc in (application processes whose background only is false)
        set appName to name of proc
        try
            repeat with win in windows of proc
                set output to output & appName & tab & (name of win) & linefeed
            end repeat
        end try
    end repeat
    return output
end tell
"""

FOCUS_SCRIPT = """
on run argv
    set appName to item 1 of argv
    set windowName to item 2 of argv
    tell application "System Events"
        tell application process appName
            set frontmost to true
            if windowName is not "" then
                perform action "AXRaise" of (first window whose name is windowName)
            end if
        end tell
    end tell
end run
"""

ACCESSIBILITY_SCRIPT = """
tell application "System Events"
    set output to ""
    set frontProcess to first application process whose frontmost is true
    set output to "Uygulama: " & (name of frontProcess) & linefeed
    set frontWindow to front window of frontProcess
    set output to output & "Pencere: " & (name of frontWindow) & linefeed
    repeat with element in (entire contents of frontWindow)
        try
            set roleName to role of element
            set elementName to name of element
            if elementName is missing value then set elementName to ""
            set output to output & roleName & tab & elementName & linefeed
        end try
    end repeat
    return output
end tell
"""


def _run(script: str, *values: str) -> ToolResult:
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    try:
        framework = _framework()
        if not _trusted(framework):
            return ToolResult.failure(ACCESSIBILITY_ERROR)
        result = subprocess.run(
            ["osascript", "-e", script, *values],
            capture_output=True,
            text=True,
            timeout=DESKTOP_COMMAND_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult.failure(f"Pencere erişimi başarısız: {exc}")
    if result.returncode:
        return ToolResult.failure(f"Pencere erişimi başarısız: {result.stderr.strip()}")
    return ToolResult(result.stdout[:12_000].strip() or "Öğe bulunamadı.")


def desktop_windows(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Çalışan uygulamaların adlandırılmış pencerelerini listele."""
    del args, context
    return _run(WINDOW_SCRIPT)


def desktop_window_focus(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Uygulama ve varsa pencere adına göre pencereyi öne getir."""
    del context
    app = require_str(args, "app")
    window = args.get("window", "")
    if not isinstance(window, str):
        return ToolResult.failure("window metin olmalı.")
    result = _run(FOCUS_SCRIPT, app, window)
    if not result.ok:
        return result
    return ToolResult(f"Öne getirildi: {app}" + (f" — {window}" if window else ""))


def desktop_accessibility(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Öndeki pencerenin erişilebilir öğelerinin rol ve adlarını oku."""
    del args, context
    return _run(ACCESSIBILITY_SCRIPT)

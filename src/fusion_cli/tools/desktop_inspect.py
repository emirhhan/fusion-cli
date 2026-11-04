"""macOS pencereleri ve erişilebilirlik öğelerini okuyan tamamlayıcı araçlar."""

from __future__ import annotations

import math
import subprocess

from ..core.desktop_settings import DesktopSettings
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .desktop import ACCESSIBILITY_ERROR, DESKTOP_COMMAND_TIMEOUT_S, _framework, _mac_only, _trusted
from .desktop_visibility import is_hidden_app

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
        set frontProcess to first application process whose frontmost is true
        if name of frontProcess is not appName then error "Requested app is not frontmost"
        set frontWindow to front window of frontProcess
        if windowName is not "" and name of frontWindow is not windowName then
            error "Requested window is not frontmost"
        end if
        set xy to position of frontWindow
        set wh to size of frontWindow
        set identityRow to (name of frontProcess) & tab & (unix id of frontProcess)
        set identityRow to identityRow & tab & (name of frontWindow)
        set geometryRow to (item 1 of xy) & tab & (item 2 of xy)
        set geometryRow to geometryRow & tab & (item 1 of wh) & tab & (item 2 of wh)
        return identityRow & tab & geometryRow
    end tell
end run
"""

ACCESSIBILITY_SCRIPT = """
tell application "System Events"
    set output to ""
    set frontProcess to first application process whose frontmost is true
    set output to "Uygulama: " & (name of frontProcess) & linefeed
    try
        set output to output & "Paket: " & (bundle identifier of frontProcess) & linefeed
    end try
    set frontWindow to front window of frontProcess
    set output to output & "Pencere: " & (name of frontWindow) & linefeed
    repeat with element in (entire contents of frontWindow)
        try
            set roleName to role of element
            set elementName to name of element
            if elementName is missing value then set elementName to ""
            set elementBounds to ""
            try
                set elementPosition to position of element
                set elementSize to size of element
                set elementBounds to tab & (item 1 of elementPosition)
                set elementBounds to elementBounds & "," & (item 2 of elementPosition)
                set elementBounds to elementBounds & "," & (item 1 of elementSize)
                set elementBounds to elementBounds & "," & (item 2 of elementSize)
                set elementBounds to elementBounds & " ekran noktası"
            end try
            set output to output & roleName & tab & elementName & elementBounds & linefeed
        end try
    end repeat
    return output
end tell
"""


_MAX_OUTPUT_CHARS = 12_000
_APP_PREFIX = "Uygulama: "
_BUNDLE_PREFIX = "Paket: "
#: Öndeki uygulama engelliyse ağaç modele verilmez (P-007).
HIDDEN_FRONT_MESSAGE = (
    "Öndeki uygulama ({app}) reddedilen ya da engelli; erişilebilirlik ağacı gösterilmez "
    "(Ayarlar › Bu bilgisayar)."
)


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
    except subprocess.TimeoutExpired:
        return ToolResult.failure(
            f"Pencere erişimi {DESKTOP_COMMAND_TIMEOUT_S} sn içinde bitmedi (büyük pencerelerde "
            "AppleScript `entire contents` dakikalar sürer). Daha hızlı ve kısmi sonuç veren "
            "desktop_background_windows + desktop_background_inspect araçlarını kullan."
        )
    except OSError as exc:
        return ToolResult.failure(f"Pencere erişimi başarısız: {exc}")
    if result.returncode:
        return ToolResult.failure(f"Pencere erişimi başarısız: {result.stderr.strip()}")
    cikti = result.stdout.strip()
    if len(cikti) > _MAX_OUTPUT_CHARS:
        return ToolResult(
            cikti[:_MAX_OUTPUT_CHARS]
            + f"\n[KIRPILDI: {len(cikti) - _MAX_OUTPUT_CHARS} karakter daha var. Tam ağaç için "
            "desktop_background_inspect kullan.]"
        )
    return ToolResult(cikti or "Öğe bulunamadı.")


def _visible_window_lines(output: str, settings: DesktopSettings) -> str:
    """`uygulama<TAB>pencere` satırlarından engelli uygulamalarınkini çıkar (başlıklar sızmasın)."""
    lines = [
        line
        for line in output.splitlines()
        if not is_hidden_app(settings, line.partition("\t")[0].strip())
    ]
    return "\n".join(lines) or "Öğe bulunamadı."


def desktop_windows(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Çalışan uygulamaların adlandırılmış pencerelerini listele (reddedilenler hariç)."""
    del args
    result = _run(WINDOW_SCRIPT)
    if not result.ok:
        return result
    return ToolResult(_visible_window_lines(result.output, context.desktop_settings))


def desktop_window_focus(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Uygulama ve varsa pencere adına göre pencereyi öne getir."""
    context.desktop.focused_window = None
    app = require_str(args, "app")
    window = args.get("window")
    window = "" if window is None else window  # `null` gönderen model "metin olmalı" hatası almasın
    if not isinstance(window, str):
        return ToolResult.failure("window metin olmalı.")
    result = _run(FOCUS_SCRIPT, app, window)
    if not result.ok:
        return result
    try:
        observed_app, raw_pid, observed_window, *geometry = result.output.split("\t")
        pid = int(raw_pid)
        x, y, width, height = map(float, geometry)
        if (
            observed_app.casefold() != app.casefold()
            or pid <= 0
            or (window and observed_window != window)
            or not all(math.isfinite(value) for value in (x, y, width, height))
            or width <= 0
            or height <= 0
        ):
            raise ValueError("identity or bounds mismatch")
    except (ValueError, TypeError):
        return ToolResult.failure(
            "Ön pencerenin kimliği ve sınırları doğrulanamadı; "
            "desktop_background_windows ile hedefi yeniden seç."
        )
    context.desktop.focused_window = (pid, x, y, width, height)
    context.desktop.frame = None
    return ToolResult(
        f"Öne getirildi ve doğrulandı: {observed_app} — {observed_window}; "
        f"pid={pid}, sınırlar=({x:g},{y:g},{width:g},{height:g}) ekran noktası. "
        "Yeni desktop_screenshot al; hedef içindeki koordinatları kullan. "
        "İşlemden sonra uygulama sonucunu yeniden incele."
    )


def _front_app(output: str) -> tuple[str, str]:
    app = bundle = ""
    for line in output.splitlines()[:3]:
        if line.startswith(_APP_PREFIX):
            app = line.removeprefix(_APP_PREFIX).strip()
        elif line.startswith(_BUNDLE_PREFIX):
            bundle = line.removeprefix(_BUNDLE_PREFIX).strip()
    return app, bundle


def desktop_accessibility(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Öndeki pencerenin erişilebilir öğelerinin rol ve adlarını oku.

    Ölçüldü (31 Ekim): öndeki uygulama ret listesinde olsa da (ör. 1Password) ağaç olduğu gibi
    dönüyordu. Ağaç önce okunur, uygulama engelliyse modele hiçbir öğe verilmez.
    """
    del args
    result = _run(ACCESSIBILITY_SCRIPT)
    if not result.ok:
        return result
    app, bundle = _front_app(result.output)
    if is_hidden_app(context.desktop_settings, app, bundle):
        return ToolResult.failure(HIDDEN_FRONT_MESSAGE.format(app=app or bundle))
    return result

"""macOS pencereleri ve erişilebilirlik öğelerini okuyan tamamlayıcı araçlar."""

from __future__ import annotations

import math
import subprocess
import time

from ..core.desktop_settings import DesktopSettings
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .desktop import ACCESSIBILITY_ERROR, DESKTOP_COMMAND_TIMEOUT_S, _framework, _mac_only, _trusted
from .desktop_visibility import is_hidden_app
from .native_desktop import invoke_sync

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
        set targetProcess to application process appName
        set targetPID to unix id of targetProcess
        tell targetProcess
            set visible to true
            set frontmost to true
            if windowName is not "" then
                set selectedWindow to first window whose name is windowName
                perform action "AXRaise" of selectedWindow
            else
                set selectedWindow to missing value
                repeat with focusAttempt from 1 to 40
                    if (unix id of targetProcess) is not targetPID then
                        error "Target application process changed"
                    end if
                    try
                        set selectedWindow to value of attribute "AXFocusedWindow" of targetProcess
                    on error
                        set selectedWindow to missing value
                    end try
                    if selectedWindow is not missing value then exit repeat
                    delay 0.05
                end repeat
                if selectedWindow is missing value then error "Actual focused window is unavailable"
            end if
        end tell
        if (unix id of targetProcess) is not targetPID then
            error "Target application process changed"
        end if
        set frontProcess to targetProcess
        set frontWindow to selectedWindow
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

FOCUS_OBSERVATION_SCRIPT = """
tell application "System Events"
    set frontProcess to first application process whose frontmost is true
    set frontWindow to value of attribute "AXFocusedWindow" of frontProcess
    if frontWindow is missing value then error "Actual focused window is unavailable"
    set xy to position of frontWindow
    set wh to size of frontWindow
    set identityRow to (name of frontProcess) & tab & (unix id of frontProcess)
    set identityRow to identityRow & tab & (name of frontWindow)
    set geometryRow to (item 1 of xy) & tab & (item 2 of xy)
    set geometryRow to geometryRow & tab & (item 1 of wh) & tab & (item 2 of wh)
    return identityRow & tab & geometryRow
end tell
"""

_FOCUS_SETTLE_S = 2.0
_FOCUS_POLL_S = 0.05


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
_WINDOW_PREFIX = "Pencere: "
_EMPTY_ACCESSIBILITY_MESSAGE = (
    "Kontrol ağacı alınamadı; başarıyla serileştirilmiş kontrol veya eylem ref'i yok. "
    "Bu çıktıdan düğme koordinatı ya da eylem yetkisi çıkarılamaz. "
    "Neden bu sonuçtan belirlenemez."
)
#: Öndeki uygulama engelliyse ağaç modele verilmez (P-007).
HIDDEN_FRONT_MESSAGE = (
    "Öndeki uygulama ({app}) reddedilen ya da engelli; erişilebilirlik ağacı gösterilmez "
    "(Ayarlar › Bu bilgisayar)."
)


def _run(script: str, *values: str, timeout_s: float = DESKTOP_COMMAND_TIMEOUT_S) -> ToolResult:
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
            timeout=min(timeout_s, DESKTOP_COMMAND_TIMEOUT_S),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ToolResult.failure(
            f"Pencere erişimi {min(timeout_s, DESKTOP_COMMAND_TIMEOUT_S):g} sn içinde bitmedi "
            "(büyük pencerelerde "
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


def _window_observation(output: str) -> tuple[str, int, str, float, float, float, float] | None:
    try:
        app, raw_pid, window, *geometry = output.split("\t")
        pid = int(raw_pid)
        x, y, width, height = map(float, geometry)
    except (ValueError, TypeError):
        return None
    if (
        not app.strip()
        or pid <= 0
        or width <= 0
        or height <= 0
        or not all(math.isfinite(value) for value in (x, y, width, height))
    ):
        return None
    return app, pid, window, x, y, width, height


def _settled_foreground(
    target: tuple[str, int, str, float, float, float, float],
    checks: dict[str, bool] | None = None,
) -> tuple[str, int, str, float, float, float, float] | None:
    deadline = time.monotonic() + _FOCUS_SETTLE_S
    while (remaining := deadline - time.monotonic()) > 0:
        result = _run(FOCUS_OBSERVATION_SCRIPT, timeout_s=remaining)
        observed = _window_observation(result.output) if result.ok else None
        if checks is not None:
            checks.clear()
            checks.update(observation_ok=result.ok, focused_window_known=observed is not None)
            if observed is not None:
                checks.update(
                    pid_matches=observed[1] == target[1], title_matches=observed[2] == target[2]
                )
        # Names may be localized aliases. The activation target's real PID and
        # selected window title are authoritative; native window ID follows.
        if observed is not None and observed[1:3] == target[1:3]:
            return observed
        time.sleep(min(_FOCUS_POLL_S, max(0.0, deadline - time.monotonic())))
    return None


def _focus_diagnostics(
    target: tuple[str, int, str, float, float, float, float],
) -> dict[str, object]:
    _app, pid, title, x, y, width, height = target
    result = invoke_sync(
        "target",
        {
            "kind": "probe",
            "request": {
                "pid": pid,
                "window_diagnostics": {"title": title, "bounds": [x, y, width, height]},
            },
        },
    )
    summary = result.get("window_diagnostics")
    return summary if isinstance(summary, dict) else {}


def desktop_window_focus(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Uygulama ve varsa pencere adına göre pencereyi öne getir."""
    # A failed focus attempt makes the previous screenshot unusable too.
    context.desktop.invalidate_capture(clear_frame=True)
    context.desktop.focus_required = True
    context.desktop.focused_window = None
    context.desktop.focused_window_id = 0
    context.desktop.focused_window_title = ""
    app = require_str(args, "app")
    window = args.get("window")
    window = "" if window is None else window  # `null` gönderen model "metin olmalı" hatası almasın
    if not isinstance(window, str):
        return ToolResult.failure("window metin olmalı.")
    result = _run(FOCUS_SCRIPT, app, window)
    if not result.ok:
        return result
    target = _window_observation(result.output)
    if target is None or (window and target[2] != window):
        return ToolResult.failure(
            "Ön pencerenin kimliği ve sınırları doğrulanamadı; "
            "desktop_background_windows ile hedefi yeniden seç."
        )
    settle_checks: dict[str, bool] = {}
    foreground = _settled_foreground(target, settle_checks)
    if foreground is None:
        return ToolResult.failure(
            "İstenen süreç/pencere süre sınırında gerçekten öne gelmedi; "
            "hedefi yeniden incele. Eski ekran görüntüsü kullanılamaz.",
            structured={
                "focus_settle": settle_checks,
                "focus_window_diagnostics": _focus_diagnostics(target),
            },
        )
    observed_app, pid, observed_window, x, y, width, height = foreground
    observation = invoke_sync("target", {"kind": "probe", "request": {}})
    observed = observation.get("window")
    checks = {
        "native_ok": observation.get("ok") is True,
        "pid_matches": observation.get("pid") == pid,
        "window_known": isinstance(observed, dict)
        and type(observed.get("id")) is int
        and observed["id"] > 0,
        "title_matches": isinstance(observed, dict) and observed.get("title") == observed_window,
        "bounds_match": isinstance(observed, dict)
        and observed.get("bounds") == [x, y, width, height],
    }
    if not all(checks.values()):
        details = ", ".join(f"{key}={str(value).lower()}" for key, value in checks.items())
        summary = _focus_diagnostics(foreground)
        return ToolResult.failure(
            "Ön pencerenin kalıcı kimliği doğrulanamadı; hedefi yeniden incele. " + details,
            structured={"focus_validation": checks, "focus_window_diagnostics": summary},
        )
    assert isinstance(observed, dict)  # established by the validated checks above
    context.desktop.focused_window = (pid, x, y, width, height)
    context.desktop.focus_required = False
    context.desktop.focused_window_id = observed["id"]
    context.desktop.focused_window_title = observed_window
    context.desktop.invalidate_capture(clear_frame=True)
    return ToolResult(
        f"Öne getirildi ve doğrulandı: {observed_app} — {observed_window}; "
        f"window_id={observed['id']}, pid={pid}, "
        f"sınırlar=({x:g},{y:g},{width:g},{height:g}) ekran noktası. "
        "İşlemden önce bu window_id ve pid ile desktop_background_inspect çağır; "
        "pencerenin güncel durumunu ve varsa display.value değerini oku. "
        "Kullanıcının yöntem sınırlarına uy. "
        "Adı belli düğmenin güncel ve tekil ref'i varsa aynı window_id, pid ve ref ile "
        "desktop_background_action (action=press) kullan. "
        "Sonucu aynı pencereyi yeniden inceleyerek doğrula. "
        "Koordinat gerekiyorsa ve kullanıcı izin veriyorsa yeni tam desktop_screenshot al; "
        "hedefin koordinatını görüntü modele ulaştıktan sonraki adımda seç.",
        structured={"target": {"window_id": observed["id"], "pid": pid}},
    )


def _front_app(output: str) -> tuple[str, str]:
    app = bundle = ""
    for line in output.splitlines()[:3]:
        if line.startswith(_APP_PREFIX):
            app = line.removeprefix(_APP_PREFIX).strip()
        elif line.startswith(_BUNDLE_PREFIX):
            bundle = line.removeprefix(_BUNDLE_PREFIX).strip()
    return app, bundle


def _has_only_accessibility_metadata(output: str) -> bool:
    """Yalnız bilinen başlık biçimini tanı; kontrol satırlarını değiştirme."""
    if output == "Öğe bulunamadı.":
        return True
    lines = output.splitlines()
    prefixes: tuple[str, ...] = (_APP_PREFIX, _BUNDLE_PREFIX, _WINDOW_PREFIX)
    if len(lines) == 2:
        prefixes = (_APP_PREFIX, _WINDOW_PREFIX)
    return len(lines) == len(prefixes) and all(
        "\t" not in line and (line == prefix.rstrip() or line.startswith(prefix))
        for line, prefix in zip(lines, prefixes, strict=True)
    )


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
    if _has_only_accessibility_metadata(result.output):
        return ToolResult(result.output + "\n[" + _EMPTY_ACCESSIBILITY_MESSAGE + "]")
    return result

"""macOS masaüstünü kullanıcı izniyle gözlemleme ve yönetme araçları."""

from __future__ import annotations

import base64
import ctypes
import subprocess
import sys
from typing import cast

from ..core.tool_content import ToolContent
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import optional_str, require_str
from .files import writable_path

SCREENSHOT_MAX_BYTES = 12_000_000
DESKTOP_COMMAND_TIMEOUT_S = 15
DESKTOP_TEXT_MAX_CHARS = 10_000
DESKTOP_SCROLL_MAX_LINES = 100
#: macOS sanal tuş kodları (ANSI). Eskiden yalnız 16 tuş vardı: `return`, `esc`, `delete`,
#: Home/End/PageUp/PageDown, F1-F12, rakamlar ve `x n t l r q p o` yoktu (Cmd+L/T/R/N/X çalışmazdı).
KEY_CODES = {
    "enter": 36, "tab": 48, "escape": 53, "backspace": 51, "space": 49,
    "left": 123, "right": 124, "down": 125, "up": 126,
    "home": 115, "end": 119, "pageup": 116, "pagedown": 121, "forwarddelete": 117,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "o": 31, "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29,
}  # fmt: skip
#: Başka araç takımlarının tuş adları.
KEY_ALIASES = {
    "return": "enter", "esc": "escape", "delete": "backspace", "del": "backspace",
    "pgup": "pageup", "page_up": "pageup", "pgdn": "pagedown", "page_down": "pagedown",
    "arrowleft": "left", "arrowright": "right", "arrowup": "up", "arrowdown": "down",
    "forward_delete": "forwarddelete",
}  # fmt: skip


def resolve_key(name: str) -> int | None:
    """Tuş adı (takma adlar dahil, büyük/küçük harf duyarsız) -> sanal tuş kodu."""
    key = name.strip().lower()
    return KEY_CODES.get(KEY_ALIASES.get(key, key))


ACCESSIBILITY_ERROR = (
    "macOS Erişilebilirlik izni yok. Sistem Ayarları > Gizlilik ve Güvenlik > "
    "Erişilebilirlik bölümünde Fusion'a izin ver; sonra uygulamayı yeniden aç."
)


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


def _mac_only() -> str | None:
    return (
        None
        if sys.platform == "darwin"
        else "Masaüstü kontrolü şu anda yalnız macOS'ta kullanılabilir."
    )


def _framework() -> ctypes.CDLL:
    return ctypes.CDLL(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
    )


def _trusted(framework: ctypes.CDLL) -> bool:
    framework.AXIsProcessTrusted.restype = ctypes.c_bool
    return bool(framework.AXIsProcessTrusted())


def desktop_apps(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Ön planda çalışabilen uygulamaların adlarını listele."""
    del args, context
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get name of '
                "(application processes whose background only is false)",
            ],
            capture_output=True,
            text=True,
            timeout=DESKTOP_COMMAND_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult.failure(f"Uygulamalar listelenemedi: {exc}")
    if result.returncode:
        return ToolResult.failure(f"Uygulamalar listelenemedi: {result.stderr.strip()}")
    names = [name.strip() for name in result.stdout.split(",") if name.strip()]
    return ToolResult("Çalışan uygulamalar: " + (", ".join(names[:80]) or "yok"))


def desktop_open(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Uygulamayı adıyla aç ve öne getir."""
    del context
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    name = require_str(args, "app")
    try:
        result = subprocess.run(
            ["open", "-a", name],
            capture_output=True,
            text=True,
            timeout=DESKTOP_COMMAND_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult.failure(f"Uygulama açılamadı: {exc}")
    if result.returncode:
        return ToolResult.failure(f"Uygulama açılamadı: {result.stderr.strip()}")
    return ToolResult(f"Uygulama açıldı: {name}")


def desktop_screenshot(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Ekranı çalışma alanına kaydet ve görseli modele aktar."""
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    target = writable_path(context, optional_str(args, "path", ".fusion/tmp/masaustu-ekrani.png"))
    if target.suffix.lower() != ".png":
        return ToolResult.failure("Ekran görüntüsü yolu .png ile bitmeli.")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        context.changes.record(target)
        result = subprocess.run(
            ["screencapture", "-x", "-t", "png", str(target)],
            capture_output=True,
            text=True,
            timeout=DESKTOP_COMMAND_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult.failure(f"Ekran görüntüsü alınamadı: {exc}")
    if result.returncode or not target.is_file():
        return ToolResult.failure(
            "Ekran görüntüsü alınamadı. Sistem Ayarları > Gizlilik ve Güvenlik > "
            "Ekran Kaydı bölümünde Fusion iznini kontrol et. " + result.stderr.strip()
        )
    if target.stat().st_size > SCREENSHOT_MAX_BYTES:
        # Çözünürlük parametresi yok: sınırı aşan görüntü kendiliğinden küçültülür (`sips`).
        shrink = subprocess.run(
            ["sips", "-Z", "1600", str(target)],
            capture_output=True,
            text=True,
            timeout=DESKTOP_COMMAND_TIMEOUT_S,
            check=False,
        )
        if shrink.returncode or target.stat().st_size > SCREENSHOT_MAX_BYTES:
            return ToolResult.failure(
                "Ekran görüntüsü sınırı aştı ve küçültülemedi; pencereyi küçült ya da "
                "desktop_background_screenshot ile tek pencere al."
            )
    context.touched.add(target)
    image = ToolContent.image("image/png", base64.b64encode(target.read_bytes()).decode("ascii"))
    return ToolResult(f"Ekran görüntüsü: {target}", content=(image,))


def _post_mouse_click(framework: ctypes.CDLL, x: int, y: int) -> None:
    framework.CGEventCreateMouseEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        _Point,
        ctypes.c_uint32,
    ]
    framework.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    framework.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    framework.CFRelease.argtypes = [ctypes.c_void_p]
    for event_type in (1, 2):  # kCGEventLeftMouseDown / kCGEventLeftMouseUp
        event = framework.CGEventCreateMouseEvent(None, event_type, _Point(x, y), 0)
        if not event:
            raise RuntimeError("Fare olayı oluşturulamadı")
        try:
            framework.CGEventPost(0, event)  # kCGHIDEventTap
        finally:
            framework.CFRelease(event)


def desktop_click(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Ekran koordinatına sol tık gönder."""
    del context
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    x, y = args.get("x"), args.get("y")
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in (x, y)):
        return ToolResult.failure("x ve y sıfırdan büyük veya eşit tam sayı olmalı.")
    try:
        framework = _framework()
        if not _trusted(framework):
            return ToolResult.failure(ACCESSIBILITY_ERROR)
        _post_mouse_click(framework, cast(int, x), cast(int, y))
    except (OSError, RuntimeError) as exc:
        return ToolResult.failure(f"Fare tıklaması gönderilemedi: {exc}")
    return ToolResult(f"Tıklandı: ({x}, {y})")


def _post_text(framework: ctypes.CDLL, value: str) -> None:
    framework.CGEventCreateKeyboardEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint16,
        ctypes.c_bool,
    ]
    framework.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    framework.CGEventKeyboardSetUnicodeString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_long,
        ctypes.POINTER(ctypes.c_uint16),
    ]
    framework.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    framework.CFRelease.argtypes = [ctypes.c_void_p]
    units = value.encode("utf-16-le")
    characters = (ctypes.c_uint16 * (len(units) // 2)).from_buffer_copy(units)
    for is_down in (True, False):
        event = framework.CGEventCreateKeyboardEvent(None, 0, is_down)
        if not event:
            raise RuntimeError("Klavye olayı oluşturulamadı")
        try:
            framework.CGEventKeyboardSetUnicodeString(event, len(characters), characters)
            framework.CGEventPost(0, event)
        finally:
            framework.CFRelease(event)


def desktop_type(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Odaklı alana Unicode metin gönder; içeriği sonuçta tekrar etme."""
    del context
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    value = require_str(args, "text")
    if len(value) > DESKTOP_TEXT_MAX_CHARS:
        return ToolResult.failure("Yazılacak metin sınırı aştı.")
    try:
        framework = _framework()
        if not _trusted(framework):
            return ToolResult.failure(ACCESSIBILITY_ERROR)
        _post_text(framework, value)
    except (OSError, RuntimeError) as exc:
        return ToolResult.failure(f"Metin yazılamadı: {exc}")
    return ToolResult(f"Odaklı alana {len(value)} karakter yazıldı.")


def _post_key(
    framework: ctypes.CDLL,
    code: int,
    *,
    command: bool,
    shift: bool,
    option: bool = False,
    control: bool = False,
) -> None:
    framework.CGEventCreateKeyboardEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint16,
        ctypes.c_bool,
    ]
    framework.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    framework.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    framework.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    framework.CFRelease.argtypes = [ctypes.c_void_p]
    flags = (
        (1 << 20 if command else 0)
        | (1 << 17 if shift else 0)
        | (1 << 19 if option else 0)
        | (1 << 18 if control else 0)
    )
    for is_down in (True, False):
        event = framework.CGEventCreateKeyboardEvent(None, code, is_down)
        if not event:
            raise RuntimeError("Klavye olayı oluşturulamadı")
        try:
            framework.CGEventSetFlags(event, flags)
            framework.CGEventPost(0, event)
        finally:
            framework.CFRelease(event)


def desktop_key(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Odaklı uygulamaya özel tuş veya Command/Shift kısayolu gönder."""
    del context
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    key = require_str(args, "key").lower()
    code = resolve_key(key)
    if code is None:
        return ToolResult.failure(
            f"Desteklenmeyen tuş: {key}. Örnekler: enter/return, esc, delete, tab, space, ok "
            "tuşları, home/end/pageup/pagedown, f1-f12, a-z, 0-9."
        )
    flags = {name: args.get(name, False) for name in ("command", "shift", "option", "control")}
    if not all(isinstance(value, bool) for value in flags.values()):
        return ToolResult.failure("command, shift, option ve control doğru/yanlış olmalı.")
    try:
        framework = _framework()
        if not _trusted(framework):
            return ToolResult.failure(ACCESSIBILITY_ERROR)
        extra = {name: True for name in ("option", "control") if flags[name]}
        _post_key(framework, code, command=flags["command"], shift=flags["shift"], **extra)
    except (OSError, RuntimeError) as exc:
        return ToolResult.failure(f"Tuş gönderilemedi: {exc}")
    return ToolResult(f"Tuş gönderildi: {key}")


def _post_scroll(framework: ctypes.CDLL, lines: int) -> None:
    framework.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p
    framework.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    framework.CFRelease.argtypes = [ctypes.c_void_p]
    event = framework.CGEventCreateScrollWheelEvent(None, 1, 1, lines)
    if not event:
        raise RuntimeError("Kaydırma olayı oluşturulamadı")
    try:
        framework.CGEventPost(0, event)
    finally:
        framework.CFRelease(event)


def desktop_scroll(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Odaklı pencerede dikey kaydır; pozitif yukarı, negatif aşağıdır."""
    del context
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    lines = args.get("lines")
    if (
        not isinstance(lines, int)
        or isinstance(lines, bool)
        or lines == 0
        or abs(lines) > DESKTOP_SCROLL_MAX_LINES
    ):
        return ToolResult.failure("lines -100 ile 100 arasında sıfır olmayan tam sayı olmalı.")
    try:
        framework = _framework()
        if not _trusted(framework):
            return ToolResult.failure(ACCESSIBILITY_ERROR)
        _post_scroll(framework, lines)
    except (OSError, RuntimeError) as exc:
        return ToolResult.failure(f"Kaydırma gönderilemedi: {exc}")
    return ToolResult(f"{abs(lines)} satır {'yukarı' if lines > 0 else 'aşağı'} kaydırıldı.")

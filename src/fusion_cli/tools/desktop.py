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
from .files import resolve_path

SCREENSHOT_MAX_BYTES = 12_000_000
DESKTOP_COMMAND_TIMEOUT_S = 15
DESKTOP_TEXT_MAX_CHARS = 10_000
DESKTOP_SCROLL_MAX_LINES = 100
KEY_CODES = {
    "enter": 36,
    "tab": 48,
    "escape": 53,
    "backspace": 51,
    "space": 49,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
    "a": 0,
    "c": 8,
    "v": 9,
    "z": 6,
    "s": 1,
    "f": 3,
    "w": 13,
}
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
    target = resolve_path(context, optional_str(args, "path", "masaustu-ekrani.png"))
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
        return ToolResult.failure("Ekran görüntüsü sınırı aştı; daha küçük çözünürlük kullan.")
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


def _post_key(framework: ctypes.CDLL, code: int, *, command: bool, shift: bool) -> None:
    framework.CGEventCreateKeyboardEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint16,
        ctypes.c_bool,
    ]
    framework.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
    framework.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    framework.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    framework.CFRelease.argtypes = [ctypes.c_void_p]
    flags = (1 << 20 if command else 0) | (1 << 17 if shift else 0)
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
    if key not in KEY_CODES:
        return ToolResult.failure("Desteklenmeyen tuş: " + key)
    command = args.get("command", False)
    shift = args.get("shift", False)
    if not isinstance(command, bool) or not isinstance(shift, bool):
        return ToolResult.failure("command ve shift doğru/yanlış olmalı.")
    try:
        framework = _framework()
        if not _trusted(framework):
            return ToolResult.failure(ACCESSIBILITY_ERROR)
        _post_key(framework, KEY_CODES[key], command=command, shift=shift)
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

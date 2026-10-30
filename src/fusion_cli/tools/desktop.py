"""macOS masaüstünü kullanıcı izniyle gözlemleme ve yönetme araçları."""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from typing import Any, cast

from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .desktop_permissions import ACCESSIBILITY, MESSAGES, permission_failure
from .key_spec import (
    HOLD_MS_MAX,
    KEY_NAME_ALIASES,
    REPEAT_MAX,
    KeyChord,
    normalize_key_name,
    parse_key_sequence,
)

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
    # Noktalama (ANSI): `cmd+-`/`cmd+=` yakınlaştırma, `cmd+,` ayarlar, `cmd+/` yorum.
    "-": 27, "=": 24, "[": 33, "]": 30, ";": 41, "'": 39, ",": 43, ".": 47, "/": 44,
    "\\": 42, "`": 50, "+": 24,
    "f13": 105, "f14": 107, "f15": 113, "f16": 106, "f17": 64, "f18": 79, "f19": 80, "f20": 90,
    "capslock": 57,
}  # fmt: skip
#: Başka araç takımlarının tuş adları (tek kaynak: `key_spec.KEY_NAME_ALIASES`).
KEY_ALIASES = KEY_NAME_ALIASES


def resolve_key(name: str) -> int | None:
    """Tuş adı (takma adlar dahil, büyük/küçük harf duyarsız) -> sanal tuş kodu."""
    return KEY_CODES.get(normalize_key_name(name))


#: Geriye uyumlu ad; metnin tek kaynağı `desktop_permissions.MESSAGES`.
ACCESSIBILITY_ERROR = MESSAGES[ACCESSIBILITY]


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
            return permission_failure(ACCESSIBILITY)
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
    hold_ms: int = 0,
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
    flags = modifier_flags(command=command, shift=shift, option=option, control=control)
    for is_down in (True, False):
        event = framework.CGEventCreateKeyboardEvent(None, code, is_down)
        if not event:
            raise RuntimeError("Klavye olayı oluşturulamadı")
        try:
            framework.CGEventSetFlags(event, flags)
            framework.CGEventPost(0, event)
        finally:
            framework.CFRelease(event)
        if is_down and hold_ms > 0:
            # Basılı tutma: tuş aşağıdayken bekle (uzun basış, oyun/kısayol tekrarı).
            time.sleep(hold_ms / 1000)


def modifier_flags(
    *, command: bool = False, shift: bool = False, option: bool = False, control: bool = False
) -> int:
    """CGEventFlags bit maskesi (kCGEventFlagMaskCommand/Shift/Alternate/Control)."""
    return (
        (1 << 20 if command else 0)
        | (1 << 17 if shift else 0)
        | (1 << 19 if option else 0)
        | (1 << 18 if control else 0)
    )


def _bounded_int(args: ToolArgs, name: str, low: int, high: int, default: int) -> int | None:
    value = args.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def _key_chords(args: ToolArgs) -> tuple[KeyChord, ...] | str:
    """Dizgi + eski boolean bayraklar → akorlar; hata metni döner."""
    raw_flags: dict[str, bool] = {}
    for name in ("command", "shift", "option", "control"):
        value = args.get(name, False)
        if not isinstance(value, bool):
            return "command, shift, option ve control doğru/yanlış olmalı."
        raw_flags[name] = value
    try:
        chords = parse_key_sequence(require_str(args, "key"))
    except ValueError as exc:
        return str(exc)
    unknown = [chord.key for chord in chords if resolve_key(chord.key) is None]
    if unknown:
        return (
            f"Desteklenmeyen tuş: {', '.join(unknown)}. Örnekler: enter/return, esc, delete, tab, "
            "space, ok tuşları, home/end/pageup/pagedown, f1-f20, a-z, 0-9, noktalama; "
            "kısayol için cmd+shift+4, dizi için 'cmd+l enter'."
        )
    return tuple(chord.with_flags(**raw_flags) for chord in chords)


def _post_chord(framework: ctypes.CDLL, chord: KeyChord, hold_ms: int) -> None:
    """Akoru `_post_key`'e geçir; yalnız açık olan ek bayraklar iletilir (test sözleşmesi)."""
    code = cast(int, resolve_key(chord.key))
    extra: dict[str, Any] = {name: True for name in ("option", "control") if getattr(chord, name)}
    if hold_ms:
        extra["hold_ms"] = hold_ms
    _post_key(framework, code, command=chord.command, shift=chord.shift, **extra)


def desktop_key(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Odaklı uygulamaya tuş dizgisi gönder: `cmd+shift+4 enter`, tekrar ve basılı tutma."""
    del context
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    chords = _key_chords(args)
    if isinstance(chords, str):
        return ToolResult.failure(chords)
    repeat = _bounded_int(args, "repeat", 1, REPEAT_MAX, 1)
    hold_ms = _bounded_int(args, "hold_ms", 0, HOLD_MS_MAX, 0)
    if repeat is None or hold_ms is None:
        return ToolResult.failure(
            f"repeat 1-{REPEAT_MAX} arasında, hold_ms 0-{HOLD_MS_MAX} arasında tam sayı olmalı."
        )
    try:
        framework = _framework()
        if not _trusted(framework):
            return permission_failure(ACCESSIBILITY)
        for _ in range(repeat):
            for chord in chords:
                _post_chord(framework, chord, hold_ms)
    except (OSError, RuntimeError) as exc:
        return ToolResult.failure(f"Tuş gönderilemedi: {exc}")
    label = ", ".join(chord.label() for chord in chords)
    suffix = f" (×{repeat})" if repeat > 1 else ""
    return ToolResult(f"Tuş gönderildi: {label}{suffix}")

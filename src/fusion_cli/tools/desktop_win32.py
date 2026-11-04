"""Windows computer use: yüzey kapısı ve girdi planları (SendInput; #430).

Claude Code: computer use masaüstü uygulamasında macOS ve Windows'ta, CLI'de yalnız macOS'ta
çalışır ("Computer use in the CLI is not available on Linux or Windows. On Windows, use Desktop
instead."); Windows'ta izin adımı yoktur, anahtar açılınca hemen etkindir. Fusion aynı kuralı
uygular: `gate` CLI'de Windows'u reddeder, masaüstü uygulamasının çekirdeğinde açar.

Bu modül saf veri üretir: fare planı (`desktop_mouse.MouseEvent`, Quartz olay türleri) ve tuş
akorları Win32 `InputSpec` dizisine çevrilir; gönderim `win32_api.Win32Api.send`'dedir. Testler
sahte API ile sınar (bu Mac'te Windows çağrısı yapılamaz).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from .key_spec import KeyChord
from .win32_api import INPUT_KEYBOARD, INPUT_MOUSE, InputSpec, Win32Like

if TYPE_CHECKING:
    from .win32_api import Win32Api

CLI_MESSAGE = (
    "Windows'ta computer use yalnız Fusion masaüstü uygulamasında kullanılabilir; CLI'de "
    "yalnız macOS'ta çalışır (Claude Code ile aynı). Fusion uygulamasını aç ve Ayarlar › "
    "Bu bilgisayar'da 'Computer use'u etkinleştir' anahtarını aç."
)
PLATFORM_MESSAGE = (
    "Masaüstü kontrolü macOS'ta ve Windows'ta (masaüstü uygulamasında) kullanılabilir; bu "
    "işletim sisteminde yok."
)

_MOVE, _LEFT_DOWN, _LEFT_UP, _RIGHT_DOWN, _RIGHT_UP = 0x1, 0x2, 0x4, 0x8, 0x10
_MIDDLE_DOWN, _MIDDLE_UP, _WHEEL, _HWHEEL = 0x20, 0x40, 0x800, 0x1000
_VIRTUAL_DESK, _ABSOLUTE = 0x4000, 0x8000
WHEEL_DELTA = 120
_KEY_EXTENDED, _KEY_UP, _KEY_UNICODE = 0x1, 0x2, 0x4
#: `desktop_mouse` Quartz olay türleri → Win32 fare bayrağı (sürükleme = basılıyken taşıma).
_QUARTZ_FLAGS = {
    5: _MOVE, 6: _MOVE, 7: _MOVE, 27: _MOVE,
    1: _LEFT_DOWN, 2: _LEFT_UP, 3: _RIGHT_DOWN, 4: _RIGHT_UP, 25: _MIDDLE_DOWN, 26: _MIDDLE_UP,
}  # fmt: skip
#: `desktop.modifier_flags` bitleri (CGEventFlags) → sanal tuş; command = Windows tuşu.
_MODIFIER_BITS = ((1 << 18, 0x11), (1 << 17, 0x10), (1 << 19, 0x12), (1 << 20, 0x5B))
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN = 0x10, 0x11, 0x12, 0x5B
#: Uzatılmış tuşlar (KEYEVENTF_EXTENDEDKEY): oklar, gezinme bloğu, Windows tuşu.
_EXTENDED = frozenset({0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B})
#: `desktop.KEY_CODES` ile aynı tuş adları → Windows sanal tuş kodu (ABD düzeni).
VK_CODES: dict[str, int] = {
    "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "backspace": 0x08, "space": 0x20,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "forwarddelete": 0x2E,
    "capslock": 0x14,
    ";": 0xBA, "=": 0xBB, "+": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF, "`": 0xC0,
    "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
    "*": 0x6A,  # VK_MULTIPLY: sayısal takımın çarpma tuşu.
    **{chr(code).lower(): code for code in range(0x41, 0x5B)},
    **{str(digit): 0x30 + digit for digit in range(10)},
    **{f"f{number}": 0x6F + number for number in range(1, 21)},
}  # fmt: skip


def active() -> bool:
    """Bu süreç Windows'ta mı? (macOS yolu değişmez.)"""
    return sys.platform == "win32"


def gate(mac_error: str | None) -> str | None:
    """Çekirdek computer use araçlarının platform kapısı: macOS hatası Windows'ta yeniden
    değerlendirilir (masaüstü uygulamasında açık, CLI'de Claude gibi kapalı)."""
    if mac_error is None or not active():
        return mac_error
    from .desktop_turn import is_app_surface

    return None if is_app_surface() else CLI_MESSAGE


@lru_cache(maxsize=1)
def _real_api() -> Win32Api:
    from .win32_api import Win32Api

    return Win32Api()


def api() -> Win32Like:
    """Win32 API (testte değiştirilir); Windows dışında `OSError`."""
    return _real_api()


def _absolute(x: float, y: float, screen: tuple[int, int, int, int]) -> tuple[int, int]:
    """Sanal masaüstü pikseli → SendInput mutlak koordinatı (0..65535)."""
    left, top, width, height = screen
    return (
        round((x - left) * 65535 / max(1, width - 1)),
        round((y - top) * 65535 / max(1, height - 1)),
    )


def modifier_vks(flags: int) -> tuple[int, ...]:
    """CGEventFlags bitleri → basılacak değiştirici sanal tuşları (ctrl, shift, alt, win)."""
    return tuple(vk for bit, vk in _MODIFIER_BITS if flags & bit)


def _key(vk: int, *, up: bool = False, gap_s: float = 0.0) -> InputSpec:
    flags = (_KEY_EXTENDED if vk in _EXTENDED else 0) | (_KEY_UP if up else 0)
    return InputSpec(INPUT_KEYBOARD, flags=flags, vk=vk, gap_s=gap_s)


def _wrap(modifiers: Sequence[int], body: list[InputSpec]) -> list[InputSpec]:
    """Değiştiricileri bas → gövde → ters sırayla bırak."""
    return [
        *(_key(vk) for vk in modifiers),
        *body,
        *(_key(vk, up=True) for vk in reversed(modifiers)),
    ]


def mouse_inputs(plan: Iterable[Any], screen: tuple[int, int, int, int]) -> list[InputSpec]:
    """`desktop_mouse.mouse_plan` olayları → SendInput fare girdileri (mutlak, sanal masaüstü)."""
    events = list(plan)
    body = []
    for event in events:
        flag = _QUARTZ_FLAGS.get(int(event.kind))
        if flag is None:
            raise ValueError(f"Bilinmeyen fare olayı: {event.kind}")
        dx, dy = _absolute(event.x, event.y, screen)
        body.append(
            InputSpec(
                INPUT_MOUSE,
                flags=flag | _MOVE | _ABSOLUTE | _VIRTUAL_DESK,
                dx=dx,
                dy=dy,
                gap_s=float(event.gap_s),
            )
        )
    flags = int(events[0].flags) if events else 0
    return _wrap(modifier_vks(flags), body)


def scroll_inputs(lines: int, delta_x: int = 0) -> list[InputSpec]:
    """`lines` pozitif yukarı (WHEEL +), `delta_x` pozitif sola (HWHEEL pozitif sağa)."""
    specs: list[InputSpec] = []
    if lines:
        specs.append(InputSpec(INPUT_MOUSE, flags=_WHEEL, data=lines * WHEEL_DELTA))
    if delta_x:
        specs.append(InputSpec(INPUT_MOUSE, flags=_HWHEEL, data=-delta_x * WHEEL_DELTA))
    return specs


def chord_inputs(chord: KeyChord, hold_ms: int = 0) -> list[InputSpec]:
    """`key_spec.KeyChord` → tuş girdileri; cmd/win = Windows tuşu, alt/option = Alt."""
    vk = VK_CODES.get(chord.key)
    if vk is None:
        raise ValueError(f"Desteklenmeyen tuş: {chord.key}")
    modifiers = [
        code
        for on, code in (
            (chord.control, VK_CONTROL),
            (chord.shift, VK_SHIFT),
            (chord.option, VK_MENU),
            (chord.command, VK_LWIN),
        )
        if on
    ]
    return _wrap(modifiers, [_key(vk, gap_s=hold_ms / 1000), _key(vk, up=True)])


def text_inputs(value: str) -> list[InputSpec]:
    """Unicode metin (KEYEVENTF_UNICODE, UTF-16 birimi başına bas/bırak); düzenden bağımsız."""
    units = value.encode("utf-16-le")
    specs: list[InputSpec] = []
    for index in range(0, len(units), 2):
        unit = int.from_bytes(units[index : index + 2], "little")
        if unit == 0x0A:
            # Satır sonu: Unicode LF çoğu denetimde yok sayılır; Enter tuşu gönderilir.
            specs.extend((_key(0x0D), _key(0x0D, up=True)))
            continue
        if unit == 0x0D:
            continue
        specs.append(InputSpec(INPUT_KEYBOARD, flags=_KEY_UNICODE, scan=unit))
        specs.append(InputSpec(INPUT_KEYBOARD, flags=_KEY_UNICODE | _KEY_UP, scan=unit))
    return specs


def send_mouse(plan: Iterable[Any]) -> None:
    sender = api()
    sender.send(mouse_inputs(plan, sender.virtual_screen()))


def send_scroll(lines: int, delta_x: int = 0) -> None:
    api().send(scroll_inputs(lines, delta_x))


def send_chord(chord: KeyChord, hold_ms: int = 0) -> None:
    api().send(chord_inputs(chord, hold_ms))


def send_text(value: str) -> None:
    api().send(text_inputs(value))

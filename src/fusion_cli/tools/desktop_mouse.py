"""Fare eylem seti (macOS Quartz; Windows SendInput, #430): tık türleri, sürükle, hover,
basılı tut, koordinatlı kaydırma (P-031).

Koordinatlar son `desktop_screenshot` görüntüsünün PİKSELİDİR; `ToolContext.desktop` çerçevesi
ekran noktasına çevirir (bkz. `core.desktop_frame`). Olaylar önce saf bir plan
(`MouseEvent` dizisi) olarak kurulur, sonra Quartz'a gönderilir; plan ctypes'sız test edilir.

Ölçüldü (31 Ekim): `desktop_click` yalnız sol tık + CG noktası alıyordu (Retina'da 2x kayma);
sağ/çift/üçlü tık, sürükle, hover, basılı tutma ve yatay/koordinatlı kaydırma yoktu.
"""

from __future__ import annotations

import ctypes
import math
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Lock, RLock, Thread

from ..core.desktop_frame import DesktopMouseAction
from ..core.tools import ToolArgs, ToolContext, ToolResult
from . import desktop_turn, desktop_win32
from .desktop import DESKTOP_SCROLL_MAX_LINES, _framework, _mac_only, _trusted, modifier_flags
from .desktop_permissions import ACCESSIBILITY, permission_failure
from .key_spec import MODIFIER_ALIASES

MOUSE_ACTIONS = (
    "click", "right_click", "double_click", "triple_click", "middle_click",
    "drag", "hover", "down", "up",
)  # fmt: skip
BUTTONS = {"left": 0, "right": 1, "middle": 2}
#: Sürüklemede başlangıç ile bitiş arasına eklenen ara nokta sayısı (uygulamalar tek sıçramayı
#: sürükleme saymaz).
DRAG_STEPS = 6
#: Ardışık olaylar arası bekleme (s): çok hızlı post edilen down/up bazı uygulamalarda düşer.
EVENT_GAP_S = 0.02
DRAG_GAP_S = 0.03

# Quartz olay türleri (CGEventType).
_MOVED = 5
_DOWN = {0: 1, 1: 3, 2: 25}
_UP = {0: 2, 1: 4, 2: 26}
_DRAGGED = {0: 6, 1: 7, 2: 27}
#: kCGMouseEventClickState: çift/üçlü tık için 2 ve 3.
_CLICK_STATE_FIELD = 1
# Serialization of physical events only; observation/ownership stays per actor.
_PHYSICAL_MOUSE_LOCK = RLock()
_PHYSICAL_BUTTON_OWNERS: dict[int, object | None] = {}
_FAILED_RELEASES: dict[int, object] = {}
_PENDING_RELEASE_LOCK = Lock()
_PENDING_RELEASES: dict[tuple[int, object], tuple[ToolContext, Callable[[ToolResult], None]]] = {}
_CLEANUP_WORKER_ACTIVE = False


def _drain_owned_releases(
    attempted: set[tuple[int, object]] | None = None,
) -> set[tuple[int, object]]:
    # Caller holds the physical mutex. No State lock is held while waiting for it.
    with _PENDING_RELEASE_LOCK:
        pending = tuple(
            (key, value)
            for key, value in _PENDING_RELEASES.items()
            if attempted is None or key not in attempted
        )
        for key, _ in pending:
            del _PENDING_RELEASES[key]
    for (button, token), (context, completed) in pending:
        result = _release_if_owned(button, token, context)
        completed(result)
        if not result.ok:
            with _PENDING_RELEASE_LOCK:
                _PENDING_RELEASES.setdefault((button, token), (context, completed))
    return {key for key, _ in pending}


@contextmanager
def _physical_mouse(context: ToolContext) -> Iterator[bool]:
    while not _PHYSICAL_MOUSE_LOCK.acquire(timeout=0.02):
        if context.cancelled.is_set() or (
            context.desktop_mouse_guard is not None
            and context.desktop_mouse_guard("", {}) is not None
        ):
            yield False
            return
    try:
        _drain_owned_releases()
        yield True
    finally:
        try:
            _drain_owned_releases()
        finally:
            _PHYSICAL_MOUSE_LOCK.release()


def request_owned_release(
    button: int, token: object, context: ToolContext, completed: Callable[[ToolResult], None]
) -> None:
    """Queue cleanup without waiting for an in-flight or hung physical OS call."""
    global _CLEANUP_WORKER_ACTIVE
    with _PENDING_RELEASE_LOCK:
        _PENDING_RELEASES[(button, token)] = (context, completed)
        if _CLEANUP_WORKER_ACTIVE:
            return
        _CLEANUP_WORKER_ACTIVE = True
    # Even an uncontended mutex may enter a hung native call. Closing a drive
    # only enqueues; no OS cleanup may execute on its event-loop thread.
    Thread(target=_cleanup_owned_releases, daemon=True, name="fusion-mouse-cleanup").start()


def _cleanup_owned_releases() -> None:
    global _CLEANUP_WORKER_ACTIVE
    # A single daemon retains cleanup responsibility behind an in-flight native
    # post. Model-action waiters remain cancellation-aware; Stop never joins this.
    attempted: set[tuple[int, object]] = set()
    with _PHYSICAL_MOUSE_LOCK:
        while True:
            attempted.update(_drain_owned_releases(attempted))
            with _PENDING_RELEASE_LOCK:
                if not any(key not in attempted for key in _PENDING_RELEASES):
                    _CLEANUP_WORKER_ACTIVE = False
                    return


def _record_physical(plan: tuple[MouseEvent, ...], context: ToolContext) -> None:
    for event in plan:
        if event.kind == _DOWN[event.button]:
            _PHYSICAL_BUTTON_OWNERS[event.button] = context.desktop_mouse_owner
        elif event.kind == _UP[event.button]:
            _PHYSICAL_BUTTON_OWNERS.pop(event.button, None)


def _physical_conflict(plan: tuple[MouseEvent, ...], context: ToolContext) -> str | None:
    for event in plan:
        if event.kind == _DOWN[event.button]:
            if event.button in _FAILED_RELEASES:
                return "Önceki basılı fare düğmesi bırakılamadı; yeni basma işlemi başlatılmadı."
            if event.button in _PHYSICAL_BUTTON_OWNERS and (
                _PHYSICAL_BUTTON_OWNERS[event.button] is not context.desktop_mouse_owner
            ):
                return "Fare düğmesini başka bir aktör basılı tutuyor; yeni basma başlatılmadı."
        elif (
            event.kind == _UP[event.button]
            and event.button in _PHYSICAL_BUTTON_OWNERS
            and (_PHYSICAL_BUTTON_OWNERS[event.button] is not context.desktop_mouse_owner)
        ):
            return "Başka aktörün basılı fare düğmesi bu işlemle bırakılamaz."
    return None


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


@dataclass(frozen=True, slots=True)
class MouseEvent:
    """Gönderilecek tek Quartz fare olayı (ekran noktası)."""

    kind: int
    x: float
    y: float
    button: int = 0
    click_state: int = 0
    flags: int = 0
    gap_s: float = EVENT_GAP_S


def mouse_plan(
    action: str,
    start: tuple[float, float],
    end: tuple[float, float] | None = None,
    *,
    button: int = 0,
    flags: int = 0,
) -> tuple[MouseEvent, ...]:
    """Eylemi olay dizisine çevir; `drag` için `end` zorunlu."""
    x, y = start
    move = MouseEvent(_MOVED, x, y, button, 0, flags)
    if action == "hover":
        return (move,)
    if action == "down":
        return (move, MouseEvent(_DOWN[button], x, y, button, 1, flags))
    if action == "up":
        return (MouseEvent(_UP[button], x, y, button, 1, flags),)
    if action == "drag":
        if end is None:
            raise ValueError("drag için to_x ve to_y gerekli.")
        events = [move, MouseEvent(_DOWN[button], x, y, button, 1, flags, DRAG_GAP_S)]
        for step in range(1, DRAG_STEPS + 1):
            ratio = step / DRAG_STEPS
            events.append(
                MouseEvent(
                    _DRAGGED[button],
                    round(x + (end[0] - x) * ratio, 1),
                    round(y + (end[1] - y) * ratio, 1),
                    button,
                    1,
                    flags,
                    DRAG_GAP_S,
                )
            )
        events.append(MouseEvent(_UP[button], end[0], end[1], button, 1, flags))
        return tuple(events)
    clicks = {"click": 1, "double_click": 2, "triple_click": 3}.get(action, 1)
    chosen = {"right_click": 1, "middle_click": 2}.get(action, button)
    events = [move]
    for state in range(1, clicks + 1):
        events.append(MouseEvent(_DOWN[chosen], x, y, chosen, state, flags))
        events.append(MouseEvent(_UP[chosen], x, y, chosen, state, flags))
    return tuple(events)


def _create_mouse_event(framework: ctypes.CDLL, event: MouseEvent) -> int:
    """Quartz fare olayını kur (GÖNDERMEZ); çağıran `CFRelease` eder. Test okunabilir."""
    framework.CGEventCreateMouseEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        _Point,
        ctypes.c_uint32,
    ]
    framework.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    framework.CGEventSetIntegerValueField.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int64,
    ]
    framework.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    framework.CFRelease.argtypes = [ctypes.c_void_p]
    handle = framework.CGEventCreateMouseEvent(
        None, event.kind, _Point(event.x, event.y), event.button
    )
    if not handle:
        raise RuntimeError("Fare olayı oluşturulamadı")
    try:
        if event.click_state:
            framework.CGEventSetIntegerValueField(handle, _CLICK_STATE_FIELD, event.click_state)
        if event.flags:
            framework.CGEventSetFlags(handle, event.flags)
    except (OSError, AttributeError):
        framework.CFRelease(handle)
        raise
    return int(handle)


def _post_mouse(framework: ctypes.CDLL, plan: tuple[MouseEvent, ...]) -> None:
    framework.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    for event in plan:
        handle = _create_mouse_event(framework, event)
        try:
            framework.CGEventPost(0, handle)  # kCGHIDEventTap
        finally:
            framework.CFRelease(handle)
        if event.gap_s:
            time.sleep(event.gap_s)


def release_owned_mouse(button: int, token: object, context: ToolContext) -> ToolResult:
    """Cleanup a previously authorized owned down; no model coordinate is used."""
    with _physical_mouse(context) as acquired:
        if not acquired:
            return ToolResult.failure(
                "Fare bırakma bekleyişi iptal edildi; sahipli temizlik sıraya alınacak."
            )
        return _release_if_owned(button, token, context)


def _release_if_owned(button: int, token: object, context: ToolContext) -> ToolResult:
    if _PHYSICAL_BUTTON_OWNERS.get(button) is not token:
        if _FAILED_RELEASES.get(button) is token:
            _FAILED_RELEASES.pop(button, None)
        return ToolResult("Bu aktöre ait basılı fare düğmesi kalmadı; yeni olay gönderilmedi.")
    try:
        result = _release_owned_mouse(button, context)
    except Exception as exc:
        result = ToolResult.failure(
            f"Fare bırakma temizliği başarısız ({type(exc).__name__}): {exc}"
        )
    if result.ok:
        _PHYSICAL_BUTTON_OWNERS.pop(button, None)
        _FAILED_RELEASES.pop(button, None)
    else:
        _FAILED_RELEASES[button] = token
    return result


def _release_owned_mouse(button: int, context: ToolContext) -> ToolResult:
    error = desktop_win32.gate(_mac_only())
    if error:
        return ToolResult.failure(error)
    if button not in _UP:
        return ToolResult.failure("Sahip olunan fare düğmesi tanınmadı.")
    try:
        if desktop_win32.active():
            desktop_win32.release_mouse_button(button)
        else:
            framework = _framework()
            if not _trusted(framework):
                return permission_failure(ACCESSIBILITY)
            framework.CGEventCreate.argtypes = [ctypes.c_void_p]
            framework.CGEventCreate.restype = ctypes.c_void_p
            framework.CGEventGetLocation.argtypes = [ctypes.c_void_p]
            framework.CGEventGetLocation.restype = _Point
            framework.CFRelease.argtypes = [ctypes.c_void_p]
            event = framework.CGEventCreate(None)
            if not event:
                return ToolResult.failure("Fare bırakılmadan önce geçerli imleç konumu okunamadı.")
            try:
                point = framework.CGEventGetLocation(event)
                x, y = float(point.x), float(point.y)
                if not (math.isfinite(x) and math.isfinite(y)):
                    return ToolResult.failure("Geçerli imleç konumu okunamadı.")
            finally:
                framework.CFRelease(event)
            _post_mouse(framework, (MouseEvent(_UP[button], x, y, button),))
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult.failure(f"Sahip olunan fare düğmesi bırakılamadı: {exc}")
    return ToolResult("Önceden basılan fare düğmesi için yalnız bırakma olayı gönderildi.")


def _coordinate(args: ToolArgs, name_x: str, name_y: str) -> tuple[float, float] | None:
    x, y = args.get(name_x), args.get(name_y)
    values = []
    for value in (x, y):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return None
        values.append(float(value))
    return values[0], values[1]


def _modifier_bits(value: object) -> int | None:
    """'cmd+shift' → CGEventFlags; boş/None → 0; bilinmeyen ad → None."""
    if value is None or value == "":
        return 0
    if not isinstance(value, str):
        return None
    flags = {}
    for token in value.replace(" ", "+").split("+"):
        field = MODIFIER_ALIASES.get(token.strip().lower())
        if field is None:
            return None
        flags[field] = True
    return modifier_flags(**flags)


NO_FRAME_MESSAGE = (
    "Bu turda henüz ekran görüntüsü yok; önce desktop_screenshot al. x,y o görüntünün pikseli "
    "olmalı (önceki turun görüntüsü geçmez)."
)


def _to_point(context: ToolContext, pixel: tuple[float, float]) -> tuple[float, float] | str:
    """Görüntü pikseli → ekran noktası; çerçeve yoksa açık hata (sessiz %10 kayma yerine).

    Ölçüldü (31 Ekim): çerçeve yokken x,y nokta sayılıyordu; REPL/TUI/masaüstü her turda yeni
    `ToolContext` kurduğu için ikinci turda önceki görüntünün pikseliyle tıklanınca Retina'da
    ~%10 kayarak yanlış öğeye gidiyor ve hata vermiyordu.
    """
    if context.desktop.focus_required:
        return (
            "Önce desktop_window_focus ile hedef kimliğini yeniden doğrula "
            "ve yeni ekran görüntüsü al."
        )
    frame = context.desktop_coordinate_frame or context.desktop.frame
    if frame is None:
        return NO_FRAME_MESSAGE
    if not frame.contains_pixel(*pixel):
        return (
            f"Koordinat görüntünün dışında: son ekran görüntüsü {frame.image_width}x"
            f"{frame.image_height} px. x,y bu görüntünün pikseli olmalı."
        )
    point = frame.to_point(*pixel)
    target = context.desktop.focused_window
    if target is not None:
        _pid, x, y, width, height = target
        if not (x <= point[0] < x + width and y <= point[1] < y + height):
            return (
                "Koordinat doğrulanmış hedef pencerenin dışında; "
                "yeni pencere incelemesi ve ekran görüntüsüyle hedefi yeniden seç."
            )
    return point


def desktop_mouse(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Fare eylemi (son ekran görüntüsünün pikseliyle): tık türleri, sürükle, hover, down/up."""
    error = desktop_win32.gate(_mac_only())
    if error:
        return ToolResult.failure(error)
    action = args.get("action", "click")
    if action not in MOUSE_ACTIONS:
        return ToolResult.failure(f"action şunlardan biri olmalı: {', '.join(MOUSE_ACTIONS)}.")
    start = _coordinate(args, "x", "y")
    if start is None:
        return ToolResult.failure("x ve y sıfırdan büyük veya eşit sayı olmalı.")
    button = BUTTONS.get(str(args.get("button", "left")))
    flags = _modifier_bits(args.get("modifiers"))
    if button is None or flags is None:
        return ToolResult.failure("button left|right|middle, modifiers 'cmd+shift' gibi olmalı.")
    end: tuple[float, float] | None = None
    if action == "drag":
        end = _coordinate(args, "to_x", "to_y")
        if end is None:
            return ToolResult.failure("drag için to_x ve to_y gerekli.")
    start_point = _to_point(context, start)
    if isinstance(start_point, str):
        return ToolResult.failure(start_point)
    end_point: tuple[float, float] | None = None
    if end is not None:
        converted = _to_point(context, end)
        if isinstance(converted, str):
            return ToolResult.failure(converted)
        end_point = converted
    busy = desktop_turn.claim_lock(context)
    if busy:
        return ToolResult.failure(busy)
    desktop_turn.foreground_action(context)
    try:
        with _physical_mouse(context) as acquired:
            if not acquired:
                return ToolResult.failure("Fare eylemi bekleyişi iptal edildi.")
            if context.cancelled.is_set():
                return ToolResult.failure("Fare eylemi iptal edildi.")
            if context.desktop_mouse_guard is not None:
                blocked = context.desktop_mouse_guard("desktop_mouse", args)
                if blocked is not None:
                    return ToolResult.failure(blocked)
            # Recompute after waiting for another actor's physical event sequence.
            start_point = _to_point(context, start)
            if isinstance(start_point, str):
                return ToolResult.failure(start_point)
            converted_end = _to_point(context, end) if end is not None else None
            if isinstance(converted_end, str):
                return ToolResult.failure(converted_end)
            end_point = converted_end
            plan = mouse_plan(action, start_point, end_point, button=button, flags=flags)
            conflict = _physical_conflict(plan, context)
            if conflict is not None:
                return ToolResult.failure(conflict)
            if desktop_win32.active():
                desktop_win32.send_mouse(plan)
            else:
                framework = _framework()
                if not _trusted(framework):
                    return permission_failure(ACCESSIBILITY)
                _post_mouse(framework, plan)
            _record_physical(plan, context)
            if context.desktop_mouse_observer is not None:
                context.desktop_mouse_observer(
                    DesktopMouseAction(
                        end_point or start_point,
                        button if action == "down" else None,
                        tuple(event.button for event in plan if event.kind == _UP[event.button]),
                    )
                )
    except (OSError, RuntimeError, ValueError) as exc:
        return ToolResult.failure(f"Fare eylemi gönderilemedi: {exc}")
    where = f"({start[0]:g}, {start[1]:g})"
    if end is not None:
        where += f" → ({end[0]:g}, {end[1]:g})"
    return ToolResult(f"Fare: {action} {where}")


def desktop_click(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Sol tık (geriye uyumlu ad); `desktop_mouse action=click` ile aynı."""
    return desktop_mouse({**args, "action": "click"}, context)


#: kCGScrollEventUnitLine ve iki tekerlek: wheel1 dikey, wheel2 yatay (pozitif sola).
_SCROLL_UNIT_LINE = 1
_SCROLL_WHEEL_COUNT = 2


def _create_scroll_event(framework: ctypes.CDLL, lines: int, delta_x: int = 0) -> int:
    """Kaydırma olayını kur (GÖNDERMEZ); çağıran `CFRelease` eder.

    `CGEventCreateScrollWheelEvent(source, units, wheelCount, wheel1, ...)` VARIADIC'tir.
    Apple Silicon'da variadic argüman yığından okunur; ctypes ancak `argtypes` sabit kısmı
    (4 öğe) kapsıyor ve fazlası tipli (`c_int32`) verildiğinde variadic çağrı üretir.
    Ölçüldü (31 Ekim, arm64 / Python 3.11): argtypes'sız çağrıda wheel2 çöp (`lines=-4,
    delta_x=0` → eksen2 -27736), 5 öğeli argtypes ile wheel2 hep 0 (`delta_x=3` → 0);
    yalnız 4 öğeli argtypes + `c_int32(delta_x)` her iki ekseni doğru taşıyor.
    """
    framework.CGEventCreateScrollWheelEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_int32,
    ]
    framework.CGEventCreateScrollWheelEvent.restype = ctypes.c_void_p
    framework.CFRelease.argtypes = [ctypes.c_void_p]
    handle = framework.CGEventCreateScrollWheelEvent(
        None, _SCROLL_UNIT_LINE, _SCROLL_WHEEL_COUNT, lines, ctypes.c_int32(delta_x)
    )
    if not handle:
        raise RuntimeError("Kaydırma olayı oluşturulamadı")
    return int(handle)


def _post_scroll(framework: ctypes.CDLL, lines: int, delta_x: int = 0) -> None:
    framework.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    event = _create_scroll_event(framework, lines, delta_x)
    try:
        framework.CGEventPost(0, event)
    finally:
        framework.CFRelease(event)


def _scroll_amount(args: ToolArgs, name: str) -> int | None:
    value = args.get(name, 0)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or abs(value) > DESKTOP_SCROLL_MAX_LINES
    ):
        return None
    return value


def desktop_scroll(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Kaydır: `lines` dikey (pozitif yukarı), `delta_x` yatay (pozitif sola), x,y imleç konumu."""
    error = desktop_win32.gate(_mac_only())
    if error:
        return ToolResult.failure(error)
    lines, delta_x = _scroll_amount(args, "lines"), _scroll_amount(args, "delta_x")
    if lines is None or delta_x is None or (lines == 0 and delta_x == 0):
        return ToolResult.failure(
            f"lines ve delta_x -{DESKTOP_SCROLL_MAX_LINES} ile {DESKTOP_SCROLL_MAX_LINES} arasında "
            "tam sayı olmalı; en az biri sıfırdan farklı."
        )
    pixel = _coordinate(args, "x", "y") if "x" in args or "y" in args else None
    if ("x" in args or "y" in args) and pixel is None:
        return ToolResult.failure("x ve y birlikte, sıfırdan büyük veya eşit sayı olmalı.")
    busy = desktop_turn.claim_lock(context)
    if busy:
        return ToolResult.failure(busy)
    desktop_turn.foreground_action(context)
    point = _to_point(context, pixel) if pixel is not None else None
    if isinstance(point, str):
        return ToolResult.failure(point)
    try:
        with _physical_mouse(context) as acquired:
            if not acquired:
                return ToolResult.failure("Kaydırma bekleyişi iptal edildi.")
            if context.cancelled.is_set():
                return ToolResult.failure("Kaydırma iptal edildi.")
            if context.desktop_mouse_guard is not None:
                blocked = context.desktop_mouse_guard("desktop_scroll", args)
                if blocked is not None:
                    return ToolResult.failure(blocked)
            point = _to_point(context, pixel) if pixel is not None else None
            if isinstance(point, str):
                return ToolResult.failure(point)
            if desktop_win32.active():
                if point is not None:
                    desktop_win32.send_mouse(mouse_plan("hover", point))
                desktop_win32.send_scroll(lines, delta_x)
            else:
                framework = _framework()
                if not _trusted(framework):
                    return permission_failure(ACCESSIBILITY)
                if point is not None:
                    _post_mouse(framework, mouse_plan("hover", point))
                _post_scroll(framework, lines, delta_x) if delta_x else _post_scroll(
                    framework, lines
                )
            if point is not None and context.desktop_mouse_observer is not None:
                context.desktop_mouse_observer(DesktopMouseAction(point))
    except (OSError, RuntimeError) as exc:
        return ToolResult.failure(f"Kaydırma gönderilemedi: {exc}")
    parts = []
    if lines:
        parts.append(f"{abs(lines)} satır {'yukarı' if lines > 0 else 'aşağı'}")
    if delta_x:
        parts.append(f"{abs(delta_x)} satır {'sola' if delta_x > 0 else 'sağa'}")
    return ToolResult(" ve ".join(parts) + " kaydırıldı.")

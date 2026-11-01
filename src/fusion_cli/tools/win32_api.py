"""Windows computer use için ince ctypes katmanı (user32/gdi32/kernel32; #430).

Bu modül YALNIZ Windows'ta yüklenir (`Win32Api()` başka platformda `OSError` verir). İş
mantığı (`desktop_win32`) saf veriyle konuşur ve bu sınıfın yerine sahte nesneyle sınanır:
burada karar yoktur, yalnız sistem çağrısı vardır. Tanıtıcılar (HWND/HDC/HANDLE) 64 bit
Windows'ta işaretçidir; kesilmesin diye her imza `c_void_p` ile bildirilir.

Not: bu dosya macOS geliştirme makinesinde derlenip çalıştırılamaz; gerçek Windows'ta elle
denenmedi. Çağrılar belgelenmiş Win32 imzalarıdır (SendInput, BitBlt/GetDIBits,
WindowFromPoint, QueryFullProcessImageNameW, CreateToolhelp32Snapshot, SetWindowsHookExW).
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .win32_types import structures

#: SendInput türleri.
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
#: GetAncestor(GA_ROOT): alt pencereden üst düzey pencereye.
_GA_ROOT = 2
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SRCCOPY_CAPTUREBLT = 0x00CC0020 | 0x40000000
_TH32CS_SNAPPROCESS = 0x2
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x80
_WH_KEYBOARD_LL = 13
_WM_KEYDOWN, _WM_SYSKEYDOWN, _WM_KEYUP, _WM_SYSKEYUP, _WM_QUIT = 0x100, 0x104, 0x101, 0x105, 0x12
VK_ESCAPE = 0x1B
#: KBDLLHOOKSTRUCT.flags: olay SendInput ile üretildi (Fusion'ın kendi Esc'i turu durdurmaz).
LLKHF_INJECTED = 0x10
#: PER_MONITOR_AWARE_V2: koordinatlar ve yakalama fiziksel piksel olur (ölçek kayması yok).
_DPI_PER_MONITOR_V2 = -4


@dataclass(frozen=True, slots=True)
class InputSpec:
    """Tek SendInput girdisi (saf veri): fare (`dx/dy/data/flags`) ya da klavye (`vk/scan`)."""

    kind: int
    flags: int = 0
    dx: int = 0
    dy: int = 0
    data: int = 0
    vk: int = 0
    scan: int = 0
    gap_s: float = 0.0


@dataclass(frozen=True, slots=True)
class WindowInfo:
    """Üst düzey pencere (z sırasıyla, en üstteki önce)."""

    hwnd: int
    pid: int
    rect: tuple[int, int, int, int]
    visible: bool
    iconic: bool
    title: str
    tool: bool
    #: GetWindowDisplayAffinity; WDA_EXCLUDEFROMCAPTURE (0x11) yakalamada görünmez.
    affinity: int = 0


class Win32Like(Protocol):
    """`Win32Api` yüzeyi; testler sahte eşini verir."""

    def send(self, specs: Sequence[InputSpec]) -> None: ...
    def virtual_screen(self) -> tuple[int, int, int, int]: ...
    def monitors(self) -> list[tuple[int, int, int, int, bool]]: ...
    def capture(self, left: int, top: int, width: int, height: int) -> bytes: ...
    def window_at(self, x: int, y: int) -> int: ...
    def foreground(self) -> int: ...
    def window_pid(self, hwnd: int) -> int: ...
    def process_image(self, pid: int) -> str | None: ...
    def windows(self) -> list[WindowInfo]: ...
    def show(self, hwnd: int, command: int) -> None: ...
    def parent_pids(self) -> dict[int, int]: ...
    def escape_hook(self, on_escape: Callable[[], None]) -> Callable[[], None] | None: ...


def _on_windows() -> bool:
    return sys.platform == "win32"


def _functype() -> Callable[..., Any]:
    """`ctypes.WINFUNCTYPE` (stdcall geri çağırım türü; yalnız Windows'ta var)."""
    factory: Callable[..., Any] = getattr(ctypes, "WINFUNCTYPE")  # noqa: B009
    return factory


def _last_error() -> int:
    return int(getattr(ctypes, "get_last_error")())  # noqa: B009


def is_physical_escape(message: int, vk: int, flags: int) -> bool:
    """Alçak düzey klavye kancası: fiziksel (enjekte edilmemiş) Esc basımı mı?"""
    if message not in (_WM_KEYDOWN, _WM_SYSKEYDOWN, _WM_KEYUP, _WM_SYSKEYUP):
        return False
    return vk == VK_ESCAPE and not flags & LLKHF_INJECTED


def _bind(user32: ctypes.CDLL, gdi32: ctypes.CDLL, kernel32: ctypes.CDLL) -> None:
    """Tanıtıcı döndüren ve alan çağrıların imzaları (64 bit kesilmesin)."""
    handle = ctypes.c_void_p
    for name in ("GetForegroundWindow", "GetDC", "GetModuleHandleW"):
        getattr(user32 if name != "GetModuleHandleW" else kernel32, name).restype = handle
    user32.GetAncestor.argtypes = [handle, ctypes.c_uint]
    user32.GetAncestor.restype = handle
    user32.GetWindowThreadProcessId.argtypes = [handle, ctypes.c_void_p]
    for name in ("IsWindowVisible", "IsIconic", "GetWindowTextLengthW"):
        getattr(user32, name).argtypes = [handle]
    user32.GetWindowTextW.argtypes = [handle, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetWindowRect.argtypes = [handle, ctypes.c_void_p]
    user32.GetWindowLongPtrW.argtypes = [handle, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowDisplayAffinity.argtypes = [handle, ctypes.c_void_p]
    user32.ShowWindowAsync.argtypes = [handle, ctypes.c_int]
    user32.ReleaseDC.argtypes = [handle, handle]
    user32.SendInput.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]
    user32.CallNextHookEx.argtypes = [handle, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.SetWindowsHookExW.restype = handle
    user32.UnhookWindowsHookEx.argtypes = [handle]
    for name in ("CreateCompatibleDC", "CreateCompatibleBitmap", "SelectObject"):
        getattr(gdi32, name).restype = handle
    gdi32.CreateCompatibleDC.argtypes = [handle]
    gdi32.CreateCompatibleBitmap.argtypes = [handle, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.argtypes = [handle, handle]
    gdi32.BitBlt.argtypes = [handle, *[ctypes.c_int] * 4, handle, ctypes.c_int, ctypes.c_int,
                             ctypes.c_uint32]  # fmt: skip
    gdi32.GetDIBits.argtypes = [handle, handle, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_uint]  # fmt: skip
    gdi32.DeleteObject.argtypes = [handle]
    gdi32.DeleteDC.argtypes = [handle]
    kernel32.OpenProcess.restype = handle
    kernel32.CloseHandle.argtypes = [handle]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        handle, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.c_void_p,
    ]  # fmt: skip
    kernel32.CreateToolhelp32Snapshot.restype = handle
    kernel32.Process32FirstW.argtypes = [handle, ctypes.c_void_p]
    kernel32.Process32NextW.argtypes = [handle, ctypes.c_void_p]


class Win32Api:
    """Gerçek Win32 çağrıları; `desktop_win32` bunu (ya da testte sahtesini) kullanır."""

    def __init__(self) -> None:
        if not _on_windows():
            raise OSError("Win32 API yalnız Windows'ta kullanılabilir.")
        loader: Any = getattr(ctypes, "WinDLL")  # noqa: B009 - yalnız Windows'ta var
        self._user32: Any = loader("user32", use_last_error=True)
        self._gdi32: Any = loader("gdi32", use_last_error=True)
        self._kernel32: Any = loader("kernel32", use_last_error=True)
        self._types: dict[str, Any] = structures()
        _bind(self._user32, self._gdi32, self._kernel32)
        try:
            self._user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(_DPI_PER_MONITOR_V2))
        except (AttributeError, OSError):
            self._user32.SetProcessDPIAware()

    # --- girdi ---------------------------------------------------------------------------
    def send(self, specs: Sequence[InputSpec]) -> None:
        """Girdileri sırayla gönder; sistem birini reddederse `OSError`."""
        input_type = self._types["Input"]
        for spec in specs:
            item = input_type()
            item.type = spec.kind
            if spec.kind == INPUT_MOUSE:
                item.u.mi.dx, item.u.mi.dy = spec.dx, spec.dy
                item.u.mi.mouseData = spec.data & 0xFFFFFFFF
                item.u.mi.dwFlags = spec.flags
            else:
                item.u.ki.wVk, item.u.ki.wScan, item.u.ki.dwFlags = spec.vk, spec.scan, spec.flags
            if self._user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item)) != 1:
                raise OSError(f"SendInput reddetti (hata {_last_error()})")
            if spec.gap_s:
                time.sleep(spec.gap_s)

    # --- ekran ---------------------------------------------------------------------------
    def virtual_screen(self) -> tuple[int, int, int, int]:
        metric = self._user32.GetSystemMetrics
        return metric(76), metric(77), metric(78), metric(79)

    def monitors(self) -> list[tuple[int, int, int, int, bool]]:
        """(sol, üst, genişlik, yükseklik, ana mı) — fiziksel piksel."""
        wintypes, info_type = self._types["wintypes"], self._types["MonitorInfo"]
        found: list[tuple[int, int, int, int, bool]] = []
        proc_type = _functype()(
            wintypes.BOOL, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t
        )

        def visit(monitor: int, _dc: int, _rect: int, _data: int) -> bool:
            info = info_type()
            info.cbSize = ctypes.sizeof(info_type)
            if self._user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
                r = info.rcMonitor
                found.append(
                    (r.left, r.top, r.right - r.left, r.bottom - r.top, bool(info.dwFlags & 1))
                )
            return True

        self._user32.EnumDisplayMonitors(None, None, proc_type(visit), 0)
        return found

    def capture(self, left: int, top: int, width: int, height: int) -> bytes:
        """Ekran dikdörtgeninin BGRA (üstten alta) baytları."""
        user32, gdi32 = self._user32, self._gdi32
        screen = user32.GetDC(None)
        if not screen:
            raise OSError("Ekran aygıt bağlamı alınamadı.")
        memory = gdi32.CreateCompatibleDC(screen)
        bitmap = gdi32.CreateCompatibleBitmap(screen, width, height)
        previous = gdi32.SelectObject(memory, bitmap)
        try:
            if not gdi32.BitBlt(
                memory, 0, 0, width, height, screen, left, top, _SRCCOPY_CAPTUREBLT
            ):
                raise OSError("BitBlt başarısız.")
            header = self._types["BitmapInfoHeader"]()
            header.biSize, header.biWidth, header.biHeight = ctypes.sizeof(header), width, -height
            header.biPlanes, header.biBitCount = 1, 32
            buffer = ctypes.create_string_buffer(width * height * 4)
            if (
                gdi32.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(header), 0)
                != height
            ):
                raise OSError("GetDIBits başarısız.")
            return buffer.raw
        finally:
            gdi32.SelectObject(memory, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory)
            user32.ReleaseDC(None, screen)

    # --- pencere / süreç -----------------------------------------------------------------
    def window_at(self, x: int, y: int) -> int:
        wintypes = self._types["wintypes"]
        self._user32.WindowFromPoint.argtypes = [wintypes.POINT]
        self._user32.WindowFromPoint.restype = ctypes.c_void_p
        child = self._user32.WindowFromPoint(wintypes.POINT(x, y))
        return int(self._user32.GetAncestor(child, _GA_ROOT) or 0) if child else 0

    def foreground(self) -> int:
        hwnd = self._user32.GetForegroundWindow()
        return int(self._user32.GetAncestor(hwnd, _GA_ROOT) or hwnd or 0) if hwnd else 0

    def window_pid(self, hwnd: int) -> int:
        pid = ctypes.c_uint32(0)
        self._user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
        return int(pid.value)

    def process_image(self, pid: int) -> str | None:
        handle = self._kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            size = ctypes.c_uint32(1024)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not self._kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return None
            return buffer.value
        finally:
            self._kernel32.CloseHandle(handle)

    def windows(self) -> list[WindowInfo]:
        """Üst düzey pencereler, z sırasıyla (EnumWindows en üsttekini önce verir)."""
        wintypes, user32 = self._types["wintypes"], self._user32
        rows: list[WindowInfo] = []
        proc_type = _functype()(wintypes.BOOL, ctypes.c_void_p, ctypes.c_ssize_t)

        def visit(hwnd: int, _data: int) -> bool:
            handle = ctypes.c_void_p(hwnd)
            rect, affinity = wintypes.RECT(), ctypes.c_uint32(0)
            user32.GetWindowRect(handle, ctypes.byref(rect))
            user32.GetWindowDisplayAffinity(handle, ctypes.byref(affinity))
            length = user32.GetWindowTextLengthW(handle)
            title = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(handle, title, length + 1)
            style = user32.GetWindowLongPtrW(handle, _GWL_EXSTYLE)
            rows.append(
                WindowInfo(
                    int(hwnd), self.window_pid(int(hwnd)),
                    (rect.left, rect.top, rect.right, rect.bottom),
                    bool(user32.IsWindowVisible(handle)), bool(user32.IsIconic(handle)),
                    title.value, bool(style & _WS_EX_TOOLWINDOW), int(affinity.value),
                )
            )  # fmt: skip
            return True

        user32.EnumWindows(proc_type(visit), 0)
        return rows

    def show(self, hwnd: int, command: int) -> None:
        self._user32.ShowWindowAsync(ctypes.c_void_p(hwnd), command)

    def parent_pids(self) -> dict[int, int]:
        """Süreç → ebeveyn süreç (Toolhelp anlık görüntüsü)."""
        kernel32, entry_type = self._kernel32, self._types["ProcessEntry"]
        snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:
            return {}
        parents: dict[int, int] = {}
        try:
            entry = entry_type()
            entry.dwSize = ctypes.sizeof(entry_type)
            ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            kernel32.CloseHandle(snapshot)
        return parents

    # --- Esc kancası ---------------------------------------------------------------------
    def escape_hook(self, on_escape: Callable[[], None]) -> Callable[[], None] | None:
        """Fiziksel Esc'i yakalayan alçak düzey kanca; Esc uygulamaya gitmez. Durdurucu döner."""
        ready, state = threading.Event(), {"thread": 0, "ok": False}
        thread = threading.Thread(
            target=self._hook_loop, args=(on_escape, ready, state), name="fusion-esc", daemon=True
        )
        thread.start()
        ready.wait(2.0)
        if not state["ok"]:
            return None

        def stop() -> None:
            self._user32.PostThreadMessageW(state["thread"], _WM_QUIT, 0, 0)
            thread.join(2.0)

        return stop

    def _hook_loop(
        self, on_escape: Callable[[], None], ready: threading.Event, state: dict[str, int]
    ) -> None:
        user32, hook_type = self._user32, self._types["KbdHook"]
        proc_type = _functype()(ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)

        def handle(code: int, message: int, data: int) -> int:
            if code == 0:
                info = ctypes.cast(data, ctypes.POINTER(hook_type)).contents
                if is_physical_escape(message, int(info.vkCode), int(info.flags)):
                    if message in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
                        on_escape()
                    return 1
            return int(user32.CallNextHookEx(None, code, message, data))

        callback = proc_type(handle)
        # Modül tanıtıcısı 64 bit: varsayılan int dönüşümü taşardı.
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            proc_type,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        state["thread"] = int(self._kernel32.GetCurrentThreadId())
        hook = user32.SetWindowsHookExW(
            _WH_KEYBOARD_LL, callback, self._kernel32.GetModuleHandleW(None), 0
        )
        state["ok"] = bool(hook)
        ready.set()
        if not hook:
            return
        message = ctypes.create_string_buffer(64)  # MSG (x64: 48 bayt)
        try:
            while user32.GetMessageW(message, None, 0, 0) > 0:
                user32.TranslateMessage(message)
                user32.DispatchMessageW(message)
        finally:
            user32.UnhookWindowsHookEx(hook)

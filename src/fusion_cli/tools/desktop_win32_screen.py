"""Windows computer use: hedef çözümü, ekran yakalama, gizleme, uygulama açma (#430).

macOS'taki Swift yardımcısının (`native_desktop`) Windows karşılığı; aynı güvenlik kuralları:

- Hedef: tıklama noktasındaki üst düzey pencerenin (WindowFromPoint + GA_ROOT) ya da öndeki
  pencerenin süreci → exe yolu. Uygulama adı exe kökü (`chrome`), "paket" exe adıdır
  (`chrome.exe`); ret listesi ve kategori tablosu ikisine de bakar. Fusion'ın süreçleri (bu
  süreç + ataları: Fusion.exe) her zaman `com.fusion.desktop` sayılır → engelli (kendi onay
  kartına tıklayamaz). Süreç adı okunamazsa hedef çözülmemiş sayılır.
- Görüntü: GDI ile yakalanır; Fusion pencereleri ve reddedilen uygulamaların pencereleri
  karartılır (Fusion penceresi WDA_EXCLUDEFROMCAPTURE ile zaten görüntü dışıysa karartılmaz).
  Karartma pencere dikdörtgenidir: önünde başka pencere olsa da o alan gösterilmez (temkinli).
- Gizleme: hedef ve Fusion dışındaki pencereler etkinleştirmeden simge durumuna küçültülür,
  tur sonunda yalnız Fusion'ın küçülttükleri geri açılır.

Gerçek Windows'ta elle denenmedi; mantık sahte API ile sınanır.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import re
import subprocess
import threading
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from ..core.desktop_settings import DesktopSettings
from . import desktop_win32
from .win32_api import Win32Like, WindowInfo

FUSION_APP = "Fusion"
FUSION_BUNDLE = "com.fusion.desktop"
#: WDA_EXCLUDEFROMCAPTURE: pencere yakalamada hiç görünmez (arkası görünür).
EXCLUDED_FROM_CAPTURE = 0x11
_SW_SHOWNOACTIVATE, _SW_SHOWMINNOACTIVE = 4, 7
_MAX_ANCESTORS = 6
_UIA_TIMEOUT_S = 8
_CREATE_NO_WINDOW = 0x08000000
_APP_NAME = re.compile(r"[\w][\w .+\-]{0,79}")
#: Küçültülen pencereler: süreç → pencereler (yalnız Fusion'ın küçülttükleri geri açılır).
_MINIMIZED: dict[int, tuple[int, ...]] = {}
_MINIMIZED_LOCK = threading.Lock()
#: UIA öğe rolü (ControlType.X) → `desktop_risk` rol adları (metin rolleri tıklamada güvenli).
_ROLE_MAP = {"Edit": "TextField", "Document": "TextArea", "ComboBox": "ComboBox"}
_UIA_SCRIPT = (
    "Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,WindowsBase;"
    "Add-Type -Namespace F -Name D -MemberDefinition "
    "'[DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware();';"
    "[F.D]::SetProcessDPIAware()|Out-Null;"
    "$e=[System.Windows.Automation.AutomationElement]::FromPoint("
    "(New-Object System.Windows.Point {x},{y}));"
    "@{{role=$e.Current.ControlType.ProgrammaticName;title=$e.Current.Name}}"
    "|ConvertTo-Json -Compress"
)


def fusion_pids(win: Win32Like | None = None) -> list[int]:
    """Bu süreç + ataları (sidecar → Fusion.exe); ebeveyn zinciri Toolhelp'ten."""
    parents = (win or desktop_win32.api()).parent_pids()
    pids, current = [os.getpid()], os.getpid()
    for _ in range(_MAX_ANCESTORS):
        parent = parents.get(current, 0)
        if parent <= 4 or parent in pids:  # 0 = boşta, 4 = System
            break
        pids.append(parent)
        current = parent
    return pids


def identity(win: Win32Like, pid: int, fusion: Sequence[int]) -> tuple[str, str] | None:
    """Süreç → (uygulama, paket); Fusion süreçleri sabit kimlik alır; okunamazsa None."""
    if pid in fusion:
        return FUSION_APP, FUSION_BUNDLE
    image = win.process_image(pid) if pid > 0 else None
    if not image:
        return None
    name = Path(image.replace("\\", "/")).name
    return Path(name).stem, name.casefold()


def element_at(x: float, y: float) -> dict[str, str]:
    """UI Automation ile noktadaki öğe (rol, ad); PowerShell yoksa ya da hata → boş."""
    script = _UIA_SCRIPT.format(x=int(x), y=int(y))
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=_UIA_TIMEOUT_S,
            check=False,
            creationflags=_CREATE_NO_WINDOW,
        )
        raw = json.loads(result.stdout or "{}") if not result.returncode else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    role = str(raw.get("role") or "").removeprefix("ControlType.")
    return {"role": _ROLE_MAP.get(role, role), "title": str(raw.get("title") or "")}


def probe(
    request: dict[str, object],
    win: Win32Like | None = None,
    element: Callable[[float, float], dict[str, str]] = element_at,
) -> dict[str, object]:
    """`native_desktop` hedef sorgusunun Windows karşılığı (nokta ya da öndeki pencere)."""
    win = win or desktop_win32.api()
    if "pid" in request:
        return {"ok": False, "metin": "Arka plan pencere araçları Windows'ta yok."}
    point = request.get("point")
    if isinstance(point, list) and len(point) == 2:
        x, y = float(point[0]), float(point[1])
        hwnd = win.window_at(round(x), round(y))
    else:
        point = None
        x = y = 0.0
        hwnd = win.foreground()
    pid = win.window_pid(hwnd) if hwnd else 0
    found = identity(win, pid, fusion_pids(win))
    if found is None:
        return {"ok": False, "metin": "Hedef pencerenin uygulaması okunamadı."}
    answer: dict[str, object] = {"ok": True, "app": found[0], "bundle": found[1], "pid": pid}
    if point is not None and found[1] != FUSION_BUNDLE:
        answer["element"] = element(x, y)
    return answer


def displays(win: Win32Like | None = None) -> list[tuple[int, int, int, int, bool]]:
    """Ekranlar, ana ekran önce (fiziksel piksel; DPI farkında süreç)."""
    rows = (win or desktop_win32.api()).monitors()
    return sorted(rows, key=lambda row: not row[4])


def _intersect(
    rect: tuple[int, int, int, int], area: tuple[int, int, int, int]
) -> tuple[int, int, int, int] | None:
    left, top, right, bottom = rect
    a_left, a_top, a_width, a_height = area
    x0, y0 = max(left, a_left), max(top, a_top)
    x1, y1 = min(right, a_left + a_width), min(bottom, a_top + a_height)
    if x1 <= x0 or y1 <= y0:
        return None
    return x0 - a_left, y0 - a_top, x1 - a_left, y1 - a_top


def mask_rects(
    win: Win32Like, settings: DesktopSettings, area: tuple[int, int, int, int]
) -> list[tuple[int, int, int, int]]:
    """Görüntüde karartılacak alanlar (yakalama alanına göre): Fusion ve reddedilenler."""
    from .desktop_visibility import is_hidden_app

    fusion = fusion_pids(win)
    names: dict[int, tuple[str, str] | None] = {}
    rects = []
    for window in win.windows():
        if not window.visible or window.iconic:
            continue
        if window.pid in fusion:
            if window.affinity == EXCLUDED_FROM_CAPTURE:
                continue
        else:
            if window.pid not in names:
                names[window.pid] = identity(win, window.pid, fusion)
            found = names[window.pid]
            if found is None or not is_hidden_app(settings, *found):
                continue
        clipped = _intersect(window.rect, area)
        if clipped is not None:
            rects.append(clipped)
    return rects


def capture_png(
    area: tuple[int, int, int, int],
    max_width: int,
    settings: DesktopSettings,
    win: Win32Like | None = None,
) -> bytes:
    """Alanı (sanal masaüstü pikseli: sol, üst, genişlik, yükseklik) yakala, karart, küçült."""
    from PIL import Image, ImageDraw

    win = win or desktop_win32.api()
    left, top, width, height = area
    raw = win.capture(left, top, width, height)
    image = Image.frombuffer("RGB", (width, height), raw, "raw", "BGRX", 0, 1).copy()
    draw = ImageDraw.Draw(image)
    for x0, y0, x1, y1 in mask_rects(win, settings, area):
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(0, 0, 0))
    if width > max_width:
        image = image.resize((max_width, max(1, round(height * max_width / width))))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _app_window(window: WindowInfo) -> bool:
    """Görev çubuğunda görünen türden uygulama penceresi (küçültülmüş olabilir)."""
    return (
        window.visible and not window.tool and bool(window.title)
        and window.title != "Program Manager"
    )  # fmt: skip


def _hideable(window: WindowInfo) -> bool:
    return _app_window(window) and not window.iconic


def hide(keep: Iterable[int], win: Win32Like | None = None) -> tuple[int, ...]:
    """Korunanlar dışındaki pencereleri etkinleştirmeden küçült; küçültülen süreçler döner."""
    win = win or desktop_win32.api()
    kept = {pid for pid in keep if pid > 0}
    grouped: dict[int, list[int]] = {}
    for window in win.windows():
        if window.pid in kept or not _hideable(window):
            continue
        win.show(window.hwnd, _SW_SHOWMINNOACTIVE)
        grouped.setdefault(window.pid, []).append(window.hwnd)
    with _MINIMIZED_LOCK:
        for pid, hwnds in grouped.items():
            _MINIMIZED[pid] = (*_MINIMIZED.get(pid, ()), *hwnds)
    return tuple(grouped)


def unhide(pids: Iterable[int], win: Win32Like | None = None) -> None:
    """Yalnız Fusion'ın küçülttüğü pencereleri etkinleştirmeden geri aç."""
    win = win or desktop_win32.api()
    with _MINIMIZED_LOCK:
        hwnds = [hwnd for pid in pids for hwnd in _MINIMIZED.pop(pid, ())]
    for hwnd in hwnds:
        win.show(hwnd, _SW_SHOWNOACTIVATE)


def running_apps(win: Win32Like | None = None) -> tuple[str, ...]:
    """Görünür, başlıklı üst düzey pencerelerin uygulama adları (exe kökü), Fusion hariç."""
    win = win or desktop_win32.api()
    fusion = fusion_pids(win)
    names: set[str] = set()
    for window in win.windows():
        if window.pid in fusion or not _app_window(window):
            continue
        found = identity(win, window.pid, fusion)
        if found is not None:
            names.add(found[0])
    return tuple(sorted(names, key=str.casefold))


def _app_paths(name: str) -> Path | None:
    """Kayıt defteri App Paths (HKCU, sonra HKLM) — Windows'un 'Çalıştır' çözümü."""
    try:
        winreg: Any = importlib.import_module("winreg")
    except ImportError:
        return None
    key_path = rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{name}.exe"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value = str(winreg.QueryValue(key, None)).strip().strip('"')
        except OSError:
            continue
        if value and Path(value).is_absolute() and Path(value).is_file():
            return Path(value)
    return None


def _start_menu(name: str) -> Path | None:
    roots = [os.environ.get("APPDATA", ""), os.environ.get("PROGRAMDATA", "")]
    wanted = f"{name}.lnk".casefold()
    for root in filter(None, roots):
        folder = Path(root) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        for link in folder.rglob("*.lnk") if folder.is_dir() else ():
            if link.name.casefold() == wanted:
                return link
    return None


def _on_path(name: str) -> Path | None:
    """PATH'te mutlak klasörler (çalışma klasörü ARANMAZ: projedeki sahte exe açılmasın)."""
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(folder) / f"{name}.exe"
        if folder and Path(folder).is_absolute() and candidate.is_file():
            return candidate
    return None


def resolve_app(raw: str) -> Path | None:
    """Uygulama adı → çalıştırılabilir ya da Başlat menüsü kısayolu; yol/URL kabul edilmez."""
    name = raw.strip()
    if name.casefold().endswith(".exe"):
        name = name[: -len(".exe")]
    if not _APP_NAME.fullmatch(name):
        return None
    return _app_paths(name) or _start_menu(name) or _on_path(name)


def open_app(raw: str) -> str:
    """Uygulamayı aç; açılan yol döner, bulunamazsa `OSError`."""
    target = resolve_app(raw)
    if target is None:
        raise OSError(f"'{raw}' adlı uygulama bulunamadı (App Paths, Başlat menüsü, PATH).")
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise OSError("Uygulama açma yalnız Windows'ta kullanılabilir.")
    startfile(str(target))
    return str(target)


def escape(
    on_escape: Callable[[], None], win: Win32Like | None = None
) -> Callable[[], None] | None:
    """Fiziksel Esc'i yakala (uygulamaya gitmez); kancanın durdurucusu ya da None."""
    return (win or desktop_win32.api()).escape_hook(on_escape)

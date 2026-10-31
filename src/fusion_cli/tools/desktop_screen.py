"""macOS ekran görüntüsü: ekran seçimi, otomatik küçültme, koordinat çerçevesi, bölge zoom (P-030).

Model tıklayacağı yeri son ekran görüntüsünün PİKSELİNDE söyler; çerçeve (`DesktopFrame`)
`ToolContext.desktop` içinde saklanır ve fare araçları noktaya çevirir. Bölge (`region`)
görüntüsü KIRPIKTIR ve çerçeveyi değiştirmez: model tam görüntüdeki koordinatla tıklar
(Chrome `zoom` ile aynı sözleşme).

Ölçüldü (31 Ekim): eski `desktop_screenshot` ham Retina pikseli veriyor, yalnız 12 MB üstünde
`sips -Z 1600` ile küçültüyor, ölçek/boyut bildirmiyor, ekran ve bölge seçemiyordu.
"""

from __future__ import annotations

import base64
import ctypes
import os
import re
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..core.desktop_frame import DesktopFrame
from ..core.desktop_settings import DesktopSettings
from ..core.tool_content import ToolContent
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import optional_str
from .desktop import DESKTOP_COMMAND_TIMEOUT_S, SCREENSHOT_MAX_BYTES, _framework, _mac_only
from .desktop_permissions import DENIED, SCREEN_RECORDING, permission_failure, probe
from .desktop_policy import capture_exclusions
from .files import writable_path
from .native_desktop import invoke_sync

DEFAULT_SCREENSHOT_PATH = ".fusion/tmp/masaustu-ekrani.png"
#: `CGGetActiveDisplayList` için üst sınır; daha fazla ekran pratikte yok.
MAX_DISPLAYS = 16
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_REGION_PATTERN = re.compile(r"\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*")
#: Süreç ağacında yukarı en çok bu kadar ata sorgulanır (fusion → zsh → Terminal.app → launchd).
MAX_ANCESTOR_DEPTH = 6


class _CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class _CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


class _CGRect(ctypes.Structure):
    _fields_ = [("origin", _CGPoint), ("size", _CGSize)]


@dataclass(frozen=True, slots=True)
class Display:
    """Bir ekranın 1 tabanlı sırası ve nokta cinsinden dikdörtgeni."""

    index: int
    x: float
    y: float
    width: float
    height: float
    is_main: bool
    #: CGDirectDisplayID; ScreenCaptureKit yakalaması bununla ekranı seçer.
    identifier: int = 0


def _displays(framework: ctypes.CDLL) -> tuple[Display, ...]:
    """`CGGetActiveDisplayList` sırası: ilk eleman ana ekrandır (screencapture -D ile aynı)."""
    framework.CGGetActiveDisplayList.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    framework.CGGetActiveDisplayList.restype = ctypes.c_int32
    framework.CGMainDisplayID.restype = ctypes.c_uint32
    framework.CGDisplayBounds.argtypes = [ctypes.c_uint32]
    framework.CGDisplayBounds.restype = _CGRect
    identifiers = (ctypes.c_uint32 * MAX_DISPLAYS)()
    count = ctypes.c_uint32(0)
    if framework.CGGetActiveDisplayList(MAX_DISPLAYS, identifiers, ctypes.byref(count)):
        raise OSError("Ekran listesi okunamadı.")
    main = framework.CGMainDisplayID()
    displays = []
    for index in range(count.value):
        bounds = framework.CGDisplayBounds(identifiers[index])
        displays.append(
            Display(
                index + 1,
                bounds.origin.x,
                bounds.origin.y,
                bounds.size.width,
                bounds.size.height,
                identifiers[index] == main,
                int(identifiers[index]),
            )
        )
    return tuple(displays)


def list_displays() -> tuple[Display, ...]:
    """Ekranlar; okunamazsa tek ekran varsayılmaz, boş döner (çağıran açık hata verir)."""
    try:
        return _displays(_framework())
    except (OSError, AttributeError):
        return ()


def png_size(data: bytes) -> tuple[int, int] | None:
    """PNG IHDR başlığından genişlik/yükseklik; PNG değilse `None`."""
    if len(data) < 24 or not data.startswith(_PNG_SIGNATURE):
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, timeout=DESKTOP_COMMAND_TIMEOUT_S, check=False
    )


def _shrink(target: Path, max_width: int) -> None:
    """Görüntü `max_width`'ten genişse `sips` ile orantılı küçült."""
    size = png_size(target.read_bytes())
    if size is None or size[0] <= max_width:
        return
    shrunk = _run(["sips", "--resampleWidth", str(max_width), str(target)])
    if shrunk.returncode:
        raise OSError(f"Ekran görüntüsü küçültülemedi: {shrunk.stderr.strip()}")


def _ancestor_pids(start: int, depth: int = MAX_ANCESTOR_DEPTH) -> tuple[int, ...]:
    """`ps -o ppid=` ile ata süreçler (launchd'ye kadar, o hariç).

    Ölçüldü (31 Ekim): dışlama listesi yalnız pid + ppid idi; terminalden koşan `fusion`ın
    ebeveyni kabuk (zsh) olduğu için Terminal.app penceresi dışlanmıyordu (ScreenCaptureKit
    kabuğu uygulama olarak listelemez, dışlamak zararsızdır). Fusion.app'te zincir sidecar →
    Fusion.app → launchd'dir.
    """
    pids: list[int] = []
    current = start
    for _ in range(depth):
        try:
            result = _run(["ps", "-o", "ppid=", "-p", str(current)])
            parent = int(result.stdout.strip())
        except (OSError, subprocess.TimeoutExpired, ValueError):
            break
        if parent <= 1:
            break
        pids.append(parent)
        current = parent
    return tuple(pids)


def _exclude_pids() -> list[int]:
    return [os.getpid(), *_ancestor_pids(os.getpid())]


def fusion_pids() -> list[int]:
    """Fusion'ın süreçleri (bu süreç + ataları): gizlemede de görünür kalırlar (P-033)."""
    return _exclude_pids()


def _native_capture(
    display: Display, max_width: int, settings: DesktopSettings | None = None
) -> bytes | None:
    """Ekranı Fusion'ın (bu süreç + ataları: Fusion.app ya da terminal) pencereleri hariç yakala.

    Başarısızsa `None`: çağıran `screencapture` ile tam ekrana düşer (P-033). Yardımcı macOS 14+
    ScreenCaptureKit ister; eski sistemde ve sahte ortamda sessizce geri düşülür.
    """
    if not display.identifier:
        return None
    names, prefixes = capture_exclusions(settings or DesktopSettings())
    request = {
        "excludePids": _exclude_pids(),
        "maxWidth": max_width,
        # Reddedilen / engelli uygulamaların pencereleri de görüntüye girmez (P-007).
        "excludeNames": list(names),
        "excludeBundlePrefixes": list(prefixes),
    }
    try:
        result = invoke_sync(
            "screen", {"kind": "display", "id": display.identifier, "request": request}
        )
    except (OSError, RuntimeError, ValueError):
        return None
    image = result.get("image") if result.get("ok") else None
    if not isinstance(image, str) or not image.startswith("data:image/png;base64,"):
        return None
    try:
        return base64.b64decode(image.split(",", 1)[1], validate=True)
    except ValueError:
        return None


def _screen_recording_denied() -> bool:
    return probe().screen_recording == DENIED


def desktop_displays(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bağlı ekranları sırası ve nokta dikdörtgeniyle listele (`desktop_screenshot display=N`)."""
    del args, context
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    displays = list_displays()
    if not displays:
        return ToolResult.failure("Ekran listesi okunamadı.")
    lines = [
        f"{d.index}: {d.width:.0f}x{d.height:.0f} nokta, sol üst ({d.x:.0f},{d.y:.0f})"
        + (" — ana ekran" if d.is_main else "")
        for d in displays
    ]
    return ToolResult("Ekranlar:\n" + "\n".join(lines))


def _parse_region(value: str | None, frame: DesktopFrame | None) -> tuple[int, ...] | str | None:
    """`region` = görüntü pikseli 'x,y,w,h'; çerçeve yoksa ekran noktası sayılır."""
    if value is None:
        return None
    match = _REGION_PATTERN.fullmatch(value)
    if match is None:
        return "region 'x,y,genişlik,yükseklik' (son ekran görüntüsünün pikseli) olmalı."
    x, y, width, height = (int(group) for group in match.groups())
    if width <= 0 or height <= 0:
        return "region genişliği ve yüksekliği sıfırdan büyük olmalı."
    if frame is not None and not frame.contains_pixel(x, y):
        return f"region görüntünün dışında: görüntü {frame.image_width}x{frame.image_height} px."
    return (x, y, width, height)


def _choose_display(args: ToolArgs, displays: tuple[Display, ...]) -> Display | str:
    value = args.get("display", 1)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return "display 1'den başlayan ekran sırası olmalı (desktop_displays ile listele)."
    if value > len(displays):
        return f"Ekran {value} yok; {len(displays)} ekran bağlı."
    return displays[value - 1]


def _display_frame(display: Display, size: tuple[int, int] | None) -> DesktopFrame:
    """Ekranın nokta dikdörtgeni + görüntü boyutu (yoksa 1 px = 1 nokta) → çerçeve."""
    image = size or (int(display.width), int(display.height))
    return DesktopFrame(
        image[0],
        image[1],
        display.x,
        display.y,
        display.width or image[0],
        display.height or image[1],
        display.index,
    )


def _capture_command(
    display: Display, region: tuple[int, ...] | None, frame: DesktopFrame | None, target: Path
) -> list[str]:
    if region is None:
        return ["screencapture", "-x", "-t", "png", "-D", str(display.index), str(target)]
    x, y, width, height = region
    source = frame if frame is not None else _display_frame(display, None)
    left, top = source.to_point(x, y)
    point_width = max(1.0, width * source.scale)
    point_height = max(1.0, height * source.scale)
    rect = f"{left:.0f},{top:.0f},{point_width:.0f},{point_height:.0f}"
    return ["screencapture", "-x", "-t", "png", "-R", rect, str(target)]


def desktop_screenshot(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Ekranı (ya da bölgesini) çalışma alanına kaydet, küçült ve çerçeveyle modele aktar."""
    error = _mac_only()
    if error:
        return ToolResult.failure(error)
    target = writable_path(context, optional_str(args, "path", DEFAULT_SCREENSHOT_PATH))
    if target.suffix.lower() != ".png":
        return ToolResult.failure("Ekran görüntüsü yolu .png ile bitmeli.")
    displays = list_displays() or (Display(1, 0.0, 0.0, 0.0, 0.0, True),)
    display = _choose_display(args, displays)
    if isinstance(display, str):
        return ToolResult.failure(display)
    previous = context.desktop.frame
    region = _parse_region(optional_str(args, "region", "") or None, previous)
    if isinstance(region, str):
        return ToolResult.failure(region)
    # Bölge son görüntünün pikseliyle verilir; o görüntü başka ekrandansa `display` çelişir.
    if (
        region is not None
        and previous is not None
        and "display" in args
        and display.index != previous.display
    ):
        return ToolResult.failure(
            f"region son görüntünün ekranına ({previous.display}) aittir, display="
            f"{display.index} ile uyuşmuyor. Önce display={display.index} ile tam görüntü al."
        )
    if _screen_recording_denied():
        return permission_failure(SCREEN_RECORDING)
    target.parent.mkdir(parents=True, exist_ok=True)
    max_width = max(1, context.desktop_screenshot_max_width)
    try:
        context.changes.record(target)
        native = (
            _native_capture(display, max_width, context.desktop_settings)
            if region is None and context.desktop_exclude_fusion_window
            else None
        )
        if native is not None:
            target.write_bytes(native)
        else:
            result = _run(_capture_command(display, region, previous, target))
            if result.returncode or not target.is_file():
                return ToolResult.failure(
                    "Ekran görüntüsü alınamadı. Sistem Ayarları > Gizlilik ve Güvenlik > "
                    "Ekran Kaydı bölümünde Fusion iznini kontrol et. " + result.stderr.strip()
                )
        _shrink(target, max_width)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolResult.failure(f"Ekran görüntüsü alınamadı: {exc}")
    data = target.read_bytes()
    size = png_size(data)
    if size is None or len(data) > SCREENSHOT_MAX_BYTES:
        return ToolResult.failure(
            "Ekran görüntüsü sınırı aştı ya da PNG değil; desktop_screenshot_max_width'i küçült."
        )
    context.touched.add(target)
    image = ToolContent.image("image/png", base64.b64encode(data).decode("ascii"))
    if region is not None:
        x, y, width, height = region
        # Ölçüldü (31 Ekim): not "büyütülmüş" diyordu; `screencapture -R` ham ekran pikseli verir,
        # `_shrink` yalnız küçültür. Bölge yakalamada Fusion penceresi dışlanmaz (bkz. docs).
        note = (
            f"Ekran görüntüsünün {x},{y} köşesinden {width}x{height} px bölgesi "
            f"({size[0]}x{size[1]} px, ham ekran pikseli; Fusion penceresi dışlanmaz). Bu görüntü "
            f"KIRPIKTIR: tıklamak için TAM ekran görüntüsündeki x,y'yi kullan (kırpığın sol üstü "
            f"tam görüntüde {x},{y})."
        )
        return ToolResult(f"{note} Dosya: {target}", content=(image,))
    frame = _display_frame(display, size)
    context.desktop.frame = frame
    return ToolResult(
        f"Ekran görüntüsü: {target}. {frame.describe()} desktop_mouse/desktop_click x,y = bu "
        "görüntünün pikseli; ayrıntı için region='x,y,w,h'.",
        content=(image,),
    )

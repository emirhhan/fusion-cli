"""Chrome sekmesinin ekran kaydı: eklentinin kareleri → GIF dosyası (P-044).

Eklenti (`recorder.js`) kareleri `captureVisibleTab` ile alır ve köprü sınırına sığan
parçalar hâlinde verir; GIF burada Pillow ile birleştirilir ve proje köküne yazılır.
`tabCapture`/`desktopCapture` izni gerekmez.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import json
import time
from pathlib import Path
from typing import Any

from ..core.errors import PathAccessError
from ..core.tools import ToolContext, ToolResult
from .files import writable_path

#: Kayıtların proje kökünde yazıldığı klasör.
RECORD_DIR = Path(".fusion") / "kayitlar"
#: Kare sayısının üst sınırı (eklenti de 120'de durur; bellek ve dosya boyutu için).
MAX_FRAMES = 240
#: Tek karenin ekranda kalma süresi için alt sınır (GIF 10 ms çözünürlükte çalışır).
MIN_FRAME_MS = 20
#: Son karenin süresi: bir önceki kareyle aynı yoksa bu kadar gösterilir.
LAST_FRAME_MS = 1000
#: GIF paleti: 256 renk dosyayı şişirir; kayıt okunabilirliği için 128 yeter.
PALETTE_COLORS = 128


def build_gif(frames: list[tuple[int, bytes]]) -> bytes:
    """Zaman damgalı JPEG karelerden döngülü GIF üret; süreler damga farkından türer.

    Senkron ve CPU yoğun (128 renk niceleme × 120 kare): çağıran `asyncio.to_thread` ile
    sarar. Ölçüldü (31 Ekim): yan panel açılıp kapanınca ya da pencere boyutlanınca kare
    boyutu değişir; Pillow farklı boyutlu kareleri tutarsız oynatır. Kareler ilk karenin
    boyutuna getirilir.
    """
    from PIL import Image

    if not frames:
        raise ValueError("GIF için kare yok.")
    images = []
    size: tuple[int, int] | None = None
    for _ts, raw in frames[:MAX_FRAMES]:
        with Image.open(io.BytesIO(raw)) as image:
            rgb = image.convert("RGB")
            size = size or rgb.size
            if rgb.size != size:
                rgb = rgb.resize(size)
            images.append(rgb.quantize(colors=PALETTE_COLORS))
    stamps = [ts for ts, _raw in frames[:MAX_FRAMES]]
    durations = [
        max(MIN_FRAME_MS, stamps[index + 1] - stamps[index]) for index in range(len(stamps) - 1)
    ]
    durations.append(durations[-1] if durations else LAST_FRAME_MS)
    out = io.BytesIO()
    images[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=False,
    )
    return out.getvalue()


async def start_recording(context: ToolContext) -> ToolResult:
    """Eklentide kare almayı başlat."""
    result = await _invoke(context, {"op": "start"})
    if isinstance(result, ToolResult):
        return result
    interval = result.get("interval_ms")
    return ToolResult(
        f"Ekran kaydı başladı (her {interval} ms bir kare, en çok {result.get('max_frames')} "
        "kare). Sayfada işlemleri yap; bitince chrome_action record 'stop' ile GIF'e çevir."
    )


def gif_name(filename: str | None) -> str:
    """Claude `export` `filename`'inden güvenli dosya adı; boşsa zaman damgalı ad."""
    base = Path(filename or "").name.strip().strip(".")
    if not base:
        return f"chrome-{time.strftime('%Y%m%d-%H%M%S')}.gif"
    return base if base.lower().endswith(".gif") else f"{base}.gif"


async def halt_recording(context: ToolContext) -> ToolResult:
    """Kare almayı durdur; kareler export ya da clear'e dek eklentide kalır (Claude gibi)."""
    stopped = await _invoke(context, {"op": "stop"})
    if isinstance(stopped, ToolResult):
        return stopped
    return ToolResult(
        f"Ekran kaydı durdu ({int(stopped.get('frames') or 0)} kare). GIF için gif_creator "
        "export, kareleri atmak için clear."
    )


async def clear_recording(context: ToolContext) -> ToolResult:
    """Kaydı durdur ve kareleri GIF yazmadan at."""
    stopped = await _invoke(context, {"op": "stop"})
    if isinstance(stopped, ToolResult):
        return stopped
    released = await _invoke(context, {"op": "release"})
    if isinstance(released, ToolResult):
        return released
    return ToolResult(f"Kayıt kareleri silindi ({int(released.get('frames') or 0)} kare).")


async def stop_recording(context: ToolContext, filename: str | None = None) -> ToolResult:
    """Kaydı durdur, kareleri parça parça çek ve GIF'i proje köküne yaz."""
    stopped = await _invoke(context, {"op": "stop"})
    if isinstance(stopped, ToolResult):
        return stopped
    total = int(stopped.get("frames") or 0)
    if total <= 0:
        return ToolResult.failure(
            "Kayıtta hiç kare yok; GIF yazılmadı. "
            f"Eklenti notu: {stopped.get('error') or 'kare alınamadı'}."
        )
    frames: list[tuple[int, bytes]] = []
    cursor: int | None = 0
    while cursor is not None:
        chunk = await _invoke(context, {"op": "fetch", "from": cursor})
        if isinstance(chunk, ToolResult):
            return chunk
        for frame in chunk.get("frames") or []:
            decoded = _decode_frame(frame)
            if decoded is not None:
                frames.append(decoded)
        following = chunk.get("next")
        cursor = following if isinstance(following, int) and following > cursor else None
    if not frames:
        return ToolResult.failure("Kareler çözülemedi; GIF yazılmadı.")
    # Kareler eklentide `release`e dek durur: GIF yazılamazsa (yazma alanı dışı, Pillow hatası)
    # `record stop` yeniden denenebilir. Ölçüldü (31 Ekim): eski eklenti son parçada oturumu
    # siliyor, hata durumunda kayıt kayboluyordu.
    try:
        data = await asyncio.to_thread(build_gif, frames)
        name = gif_name(filename)
        target = writable_path(context, str(RECORD_DIR / name))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    except (OSError, ValueError, PathAccessError) as exc:
        return ToolResult.failure(
            f"GIF yazılamadı: {exc} Kareler eklentide tutuldu; sorunu giderip "
            "chrome_action record 'stop' ile yeniden deneyebilirsin."
        )
    await _release(context)
    relative = _relative(target, context.root)
    skipped = int(stopped.get("skipped") or 0)
    reason = stopped.get("skip_reason") or "kaydedilen sekme etkin değildi"
    note = f" {skipped} kare atlandı ({reason})." if skipped > 0 else ""
    return ToolResult(
        f"Ekran kaydı GIF olarak yazıldı: {relative} ({len(frames)} kare, "
        f"{stopped.get('duration_ms', 0)} ms, {len(data) // 1024} KB).{note} "
        f"Kaynak sayfa: {stopped.get('url', '')}"
    )


async def _release(context: ToolContext) -> None:
    """Eklentideki kareleri bırak; başarısızlık GIF'in yazılmış olmasını değiştirmez."""
    await _invoke(context, {"op": "release"})


def _decode_frame(frame: object) -> tuple[int, bytes] | None:
    if not isinstance(frame, dict) or not isinstance(frame.get("image"), str):
        return None
    try:
        raw = base64.b64decode(frame["image"], validate=True)
    except (ValueError, binascii.Error):
        return None
    stamp = frame.get("t")
    return (int(stamp) if isinstance(stamp, (int, float)) else 0, raw)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


async def _invoke(context: ToolContext, data: dict[str, Any]) -> dict[str, Any] | ToolResult:
    """`record` komutunu eklentiye gönder; hata ToolResult olarak döner."""
    if context.chrome is None:
        return ToolResult.failure("Chrome eklentisi bağlı değil.")
    try:
        result = await context.chrome.invoke("record", data)
    except (ConnectionError, TimeoutError) as exc:
        return ToolResult.failure(str(exc))
    except (ValueError, RuntimeError, OSError) as exc:
        return ToolResult.failure(f"Chrome köprüsü hatası: {type(exc).__name__}: {exc}")
    if not result.get("ok"):
        return ToolResult.failure(str(result.get("hata") or "Kayıt komutu başarısız."))
    veri = result.get("veri")
    if not isinstance(veri, dict):
        return ToolResult.failure(f"Chrome kayıt yanıtı geçersiz: {json.dumps(veri)[:200]}")
    return veri

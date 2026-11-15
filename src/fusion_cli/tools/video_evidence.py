"""Render edilen videonun GERÇEK dosya kanıtı: boyut, süre, çözünürlük, çözülebilirlik.

Ölçüldü (29 Ekim): kapanış yalnız çıktı yolunun varlığına, siyah ve donuk bölümlere
bakıyordu. 1 baytlık bir `.mp4` ya da planlanandan farklı süre/çözünürlükte bir dosya
"video var" diye geçiyordu; ffmpeg/ffprobe hiç yoksa ölçüm sessizce atlanıyordu. Burada
ölçüm ya yapılır ya da AÇIKÇA `None` (not_measured) döner; sessiz geçiş yoktur.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

#: ffprobe/ffmpeg çağrısının azami süresi (sn).
TOOL_TIMEOUT_S = 120.0
#: Planlanan süreden izin verilen sapma: en az yarım saniye (kodek/konteyner payı).
DURATION_TOLERANCE_S = 0.5
#: Kare hızı sapma payı (ör. 29,97 ile 30).
FPS_TOLERANCE = 0.5


@dataclass(frozen=True, slots=True)
class VideoFacts:
    size_bytes: int
    duration_s: float
    width: int
    height: int
    fps: float | None

    def summary(self) -> str:
        fps = f", {self.fps:g} fps" if self.fps else ""
        return (
            f"{self.width}x{self.height}{fps}, {self.duration_s:.1f} sn, "
            f"{self.size_bytes / 1_048_576:.2f} MB"
        )


@dataclass(frozen=True, slots=True)
class ExpectedVideo:
    """Host planının söylediği değerler (Remotion kit sözleşmesi)."""

    width: int
    height: int
    fps: float
    duration_s: float


class VideoUnreadableError(ValueError):
    """Dosya var ama oynatılabilir bir video değil."""


async def _run(*command: str) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=TOOL_TIMEOUT_S)
    except TimeoutError:
        process.kill()
        raise
    return (
        process.returncode if process.returncode is not None else -1,
        out.decode("utf-8", errors="replace"),
        err.decode("utf-8", errors="replace"),
    )


def _fraction(raw: str) -> float | None:
    try:
        value = float(Fraction(raw))
    except (ValueError, ZeroDivisionError):
        return None
    return value if value > 0 else None


def parse_ffprobe(payload: str, size_bytes: int) -> VideoFacts:
    """`ffprobe -print_format json` çıktısından video gerçekleri; bozuksa hata."""
    try:
        data = json.loads(payload)
    except ValueError as error:
        raise VideoUnreadableError("ffprobe çıktısı okunamadı") from error
    streams = data.get("streams", []) if isinstance(data, dict) else []
    video = next(
        (s for s in streams if isinstance(s, dict) and s.get("codec_type") == "video"), None
    )
    if video is None:
        raise VideoUnreadableError("dosyada video akışı yok")
    try:
        width, height = int(video["width"]), int(video["height"])
        duration = float(data.get("format", {}).get("duration", video.get("duration")))
    except (KeyError, TypeError, ValueError) as error:
        raise VideoUnreadableError("video süre/çözünürlük bilgisi eksik") from error
    if width <= 0 or height <= 0 or duration <= 0:
        raise VideoUnreadableError("video süresi ya da çözünürlüğü sıfır")
    return VideoFacts(size_bytes, duration, width, height, _fraction(video.get("r_frame_rate", "")))


async def read_video_facts(path: Path) -> VideoFacts | None:
    """Gerçek dosyadan ölçüm. ffprobe yoksa None (not_measured); bozuksa VideoUnreadableError."""
    try:
        size = (await asyncio.to_thread(path.stat)).st_size
    except OSError as error:
        raise VideoUnreadableError(f"dosya okunamadı: {error}") from error
    if size == 0:
        raise VideoUnreadableError("dosya boş (0 bayt)")
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    try:
        code, out, _ = await _run(
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_entries",
            "stream=codec_type,width,height,r_frame_rate,duration:format=duration",
            str(path),
        )
    except (OSError, TimeoutError):
        return None
    if code != 0:
        raise VideoUnreadableError("ffprobe dosyayı video olarak okuyamadı")
    return parse_ffprobe(out, size)


async def decode_errors(path: Path) -> str | None:
    """Tüm kareleri çöz; ffmpeg hata basarsa ilk satırlar. Ölçülemezse None."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    try:
        code, _, err = await _run(ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-")
    except (OSError, TimeoutError):
        return None
    if code == 0 and not err.strip():
        return ""
    return " | ".join(err.strip().splitlines()[:2]) or f"ffmpeg çıkış kodu {code}"


def mismatches(facts: VideoFacts, expected: ExpectedVideo) -> list[str]:
    """Plan ile dosya arasındaki farklar (boşsa uyumlu)."""
    farklar: list[str] = []
    if (facts.width, facts.height) != (expected.width, expected.height):
        farklar.append(
            f"çözünürlük {facts.width}x{facts.height}, planlanan {expected.width}x{expected.height}"
        )
    if abs(facts.duration_s - expected.duration_s) > DURATION_TOLERANCE_S:
        farklar.append(f"süre {facts.duration_s:.1f} sn, planlanan {expected.duration_s:.1f} sn")
    if facts.fps is not None and abs(facts.fps - expected.fps) > FPS_TOLERANCE:
        farklar.append(f"kare hızı {facts.fps:g} fps, planlanan {expected.fps:g} fps")
    return farklar

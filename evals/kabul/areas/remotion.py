"""Kabul alanı `remotion`: Remotion ile 10 sn'lik 1920x1080 30 fps tanıtım videosu.

Denetçi videoyu `ffprobe`/`ffmpeg` ile bağımsız ölçer: süre, çözünürlük, fps, üç
örnek karenin boş olmaması ve birbirinden farklı olması; kaynakta Remotion'da render'da
çalışmayan CSS hareketinin bulunmaması ve `useCurrentFrame` kullanımı.

Aşağıdaki eşikler BAŞLANGIÇ eşikleridir; taban ölçümüyle sabitlenecek.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evals.kabul.areas._pixels import changed_pixel_ratio, luminance_variance
from evals.kabul.areas._sources import iter_files
from evals.kabul.model import Area, Check, Inspection

#: Ajana verilen görev. Süslü parantez yok: sürücü yer tutucu doldurur.
TASK = (
    "Remotion ile 10 saniyelik, 1920x1080 çözünürlüklü, 30 fps bir ürün tanıtım videosu "
    "üret: bir başlık sahnesi, üç özellik sahnesi ve bir kapanış sahnesi olsun. Hareketi "
    "Remotion'un kare tabanlı API'leriyle kur. Videoyu `out/video.mp4` olarak render et."
)

TIMEOUT_S = 5400.0
REQUIRED_EXECUTABLES = ("node", "npx", "ffprobe", "ffmpeg")
VIDEO_PATH = Path("out") / "video.mp4"
#: Beklenen süre ve payı (sn). ±0,5: kare yuvarlaması ve kodlayıcı payı.
EXPECTED_DURATION_S = 10.0
DURATION_TOLERANCE_S = 0.5
EXPECTED_WIDTH = 1920
EXPECTED_HEIGHT = 1080
EXPECTED_FPS = 30.0
#: Kesirli fps (ör. 30000/1001) ile 30'u ayıran pay.
FPS_TOLERANCE = 0.01
#: Örnek kare anları (sn): açılış, orta, kapanış.
SAMPLE_TIMES_S = (0.5, 5.0, 9.5)
#: Karenin "boş değil" sayılması için parlaklık varyansı alt sınırı (tek renk = 0;
#: koyu zemin üstüne tek başlık bile yüzlerce verir).
MIN_FRAME_VARIANCE = 25.0
#: İki örnek kare arasında değişen piksel oranı alt sınırı. Amaç DONMUŞ videoyu
#: yakalamak (orada ~0). Ölçüldü (4 Ekim taban): koyu zeminde başlık sahnesi ile
#: kapanış sahnesi gerçekten farklı kareler olduğu hâlde oran 0,019 çıktı; %2 sade
#: tasarımı "donuk" sayıyordu. Tasarım kalitesi bu maddenin işi değildir.
MIN_FRAME_DIFFERENCE = 0.005
#: ffprobe/ffmpeg alt süreç zaman aşımı (sn).
TOOL_TIMEOUT_S = 120

#: Videodan ölçülen maddelerin adları (sıra: süre, boyut, fps, boş değil, farklı).
VIDEO_CHECK_NAMES = (
    f"süre {EXPECTED_DURATION_S:g}±{DURATION_TOLERANCE_S:g} sn",
    f"{EXPECTED_WIDTH}x{EXPECTED_HEIGHT}",
    f"fps {EXPECTED_FPS:g}",
    "örnek kareler boş değil",
    "örnek kareler birbirinden farklı",
)

_SOURCE_SUFFIXES = frozenset({".ts", ".tsx"})
_LINE_COMMENT = re.compile(r"(?<![:\"'])//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CURRENT_FRAME = re.compile(r"\buseCurrentFrame\b")
#: Remotion'da render sırasında çalışmayan (zamana bağlı) CSS hareket kalıpları.
FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("transition:", re.compile(r"\btransition\s*:")),
    ("animation:", re.compile(r"\banimation\s*:")),
    ("animationName", re.compile(r"\banimation-?[nN]ame\b")),
    ("@keyframes", re.compile(r"@keyframes\b")),
    ("tailwind animate-", re.compile(r"\banimate-[\w\[]")),
    (
        "tailwind transition-*",
        re.compile(r"\btransition-(?:all|colors|opacity|transform|shadow|none)\b"),
    ),
)


class VideoReadError(RuntimeError):
    """Video ffprobe/ffmpeg ile okunamadı (bozuk dosya)."""


@dataclass(frozen=True, slots=True)
class VideoProbe:
    """ffprobe'dan okunan video özellikleri."""

    duration_s: float
    width: int
    height: int
    fps: float


def _as_float(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    raise ValueError(f"sayı beklendi: {value!r}")


def _parse_fraction(text: str) -> float:
    numerator, _, denominator = text.partition("/")
    divisor = _as_float(denominator) if denominator else 1.0
    if divisor == 0:
        raise ValueError("fps paydası sıfır")
    return _as_float(numerator) / divisor


def parse_probe(output: str) -> VideoProbe:
    """`ffprobe -of json` çıktısını ayrıştır; eksik/bozuk alanda `ValueError` fırlat."""
    document = cast("dict[str, object]", json.loads(output))
    streams = cast("list[dict[str, object]]", document.get("streams") or [])
    if not streams:
        raise ValueError("video akışı yok")
    stream = streams[0]
    container = cast("dict[str, object]", document.get("format") or {})
    duration = stream.get("duration", container.get("duration"))
    return VideoProbe(
        duration_s=_as_float(duration),
        width=int(_as_float(stream.get("width"))),
        height=int(_as_float(stream.get("height"))),
        fps=_parse_fraction(str(stream.get("r_frame_rate", ""))),
    )


def probe_video(path: Path) -> VideoProbe:
    """Videoyu `ffprobe` ile ölç."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,duration:format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, timeout=TOOL_TIMEOUT_S, check=False
        )
        if done.returncode != 0:
            raise VideoReadError(done.stderr.strip()[:160] or "ffprobe başarısız")
        return parse_probe(done.stdout)
    except (subprocess.TimeoutExpired, ValueError) as error:
        raise VideoReadError(f"ffprobe okunamadı: {error}") from error


def extract_frame(path: Path, at_s: float) -> bytes | None:
    """`at_s` saniyesindeki kareyi PNG olarak çıkar; çıkmazsa `None`."""
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-ss",
        f"{at_s:.3f}",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]
    try:
        done = subprocess.run(command, capture_output=True, timeout=TOOL_TIMEOUT_S, check=False)
    except subprocess.TimeoutExpired:
        return None
    return done.stdout or None


def strip_ts_comments(text: str) -> str:
    """TS/TSX metninden yorumları ayıkla (yorumdaki sözcük ihlal sayılmasın)."""
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def find_css_motion_usage(text: str) -> tuple[str, ...]:
    """Metinde Remotion'da çalışmayan CSS hareket kalıplarını ara; bulunan adları ver."""
    clean = strip_ts_comments(text)
    return tuple(label for label, pattern in FORBIDDEN_PATTERNS if pattern.search(clean))


def _spec_checks(probe: VideoProbe) -> tuple[Check, Check, Check]:
    duration_ok = abs(probe.duration_s - EXPECTED_DURATION_S) <= DURATION_TOLERANCE_S
    size_ok = (probe.width, probe.height) == (EXPECTED_WIDTH, EXPECTED_HEIGHT)
    fps_ok = abs(probe.fps - EXPECTED_FPS) <= FPS_TOLERANCE
    return (
        Check(
            f"süre {EXPECTED_DURATION_S:g}±{DURATION_TOLERANCE_S:g} sn",
            duration_ok,
            f"ölçülen süre {probe.duration_s:.2f} sn",
        ),
        Check(
            f"{EXPECTED_WIDTH}x{EXPECTED_HEIGHT}",
            size_ok,
            f"ölçülen {probe.width}x{probe.height}",
        ),
        Check(f"fps {EXPECTED_FPS:g}", fps_ok, f"ölçülen {probe.fps:.3f} fps"),
    )


def _frame_checks(path: Path) -> tuple[Check, Check]:
    frames = [extract_frame(path, at) for at in SAMPLE_TIMES_S]
    if any(frame is None for frame in frames):
        reason = "kare çıkarılamadı: " + ", ".join(
            f"{at:g}s" for at, frame in zip(SAMPLE_TIMES_S, frames, strict=True) if frame is None
        )
        return Check("örnek kareler boş değil", False, reason), Check(
            "örnek kareler birbirinden farklı", False, reason
        )
    pngs = [frame for frame in frames if frame is not None]
    variances = [luminance_variance(png) for png in pngs]
    ratios = [
        changed_pixel_ratio(pngs[first], pngs[second])
        for first in range(len(pngs))
        for second in range(first + 1, len(pngs))
    ]
    shown_variances = ", ".join(
        f"{at:g}s={value:.1f}" for at, value in zip(SAMPLE_TIMES_S, variances, strict=True)
    )
    blank = Check(
        "örnek kareler boş değil",
        min(variances) >= MIN_FRAME_VARIANCE,
        f"parlaklık varyansı {shown_variances} (eşik {MIN_FRAME_VARIANCE:g})",
    )
    distinct = Check(
        "örnek kareler birbirinden farklı",
        min(ratios) >= MIN_FRAME_DIFFERENCE,
        f"en küçük değişen piksel oranı {min(ratios):.3f} (eşik {MIN_FRAME_DIFFERENCE})",
    )
    return blank, distinct


def _video_checks(path: Path) -> tuple[Check, ...]:
    try:
        probe = probe_video(path)
    except VideoReadError as error:
        reason = f"video okunamadı: {error}"
        return tuple(Check(name, False, reason) for name in VIDEO_CHECK_NAMES)
    return (*_spec_checks(probe), *_frame_checks(path))


def _source_checks(root: Path) -> tuple[Check, Check]:
    files = list(iter_files(root / "src", _SOURCE_SUFFIXES)) if (root / "src").is_dir() else []
    texts = [path.read_text(encoding="utf-8", errors="replace") for path in files]
    if not files:
        reason = "src/ altında .ts/.tsx dosyası yok"
        return (
            Check("src'de CSS transition/animation kullanımı yok", False, reason),
            Check("useCurrentFrame kullanılıyor", False, reason),
        )
    violations = sorted({label for text in texts for label in find_css_motion_usage(text)})
    uses = sum(len(_CURRENT_FRAME.findall(strip_ts_comments(text))) for text in texts)
    return (
        Check(
            "src'de CSS transition/animation kullanımı yok",
            not violations,
            f"{len(files)} dosyada {len(violations)} tür ihlal"
            + (f": {', '.join(violations)}" if violations else ""),
        ),
        Check("useCurrentFrame kullanılıyor", uses >= 1, f"{uses} kullanım"),
    )


def _missing_video_checks() -> tuple[Check, ...]:
    reason = f"{VIDEO_PATH.as_posix()} yok (ajan çıktı üretmedi)"
    return (
        Check(f"{VIDEO_PATH.as_posix()} var", False, reason),
        *(Check(name, False, reason) for name in VIDEO_CHECK_NAMES),
    )


def inspect(workdir: Path, values: Mapping[str, str]) -> Inspection:
    """Ajanın render ettiği videoyu ve Remotion kaynağını bağımsız ölç."""
    video = workdir / VIDEO_PATH
    source = _source_checks(workdir)
    if not video.is_file():
        return Inspection(checks=(*_missing_video_checks(), *source))
    missing = [tool for tool in ("ffprobe", "ffmpeg") if shutil.which(tool) is None]
    if missing:
        return Inspection(invalid_reason=f"denetçi araçları yok: {', '.join(missing)}")
    present = Check(f"{VIDEO_PATH.as_posix()} var", True, f"{video.stat().st_size} bayt")
    return Inspection(checks=(present, *_video_checks(video), *source))


AREA = Area(
    name="remotion",
    task=TASK,
    timeout_s=TIMEOUT_S,
    inspect=inspect,
    required_executables=REQUIRED_EXECUTABLES,
)

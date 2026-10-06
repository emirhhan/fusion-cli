"""İstenen çıktı dosyası istenen yerde mi: kullanıcının yazdığı yol kapanışta aranır.

Ölçüldü (6 Ekim 2026, dalga23 Remotion): görev "Videoyu `out/video.mp4` olarak render
et" dedi. Fusion projeyi `video/` alt klasörüne kurdu, doğru videoyu
`video/out/video.mp4` olarak üretti ve "tamamlandı" dedi; istenen yerde dosya yoktu ve
kullanıcının (ve denetçinin) gözünde iş hiç yapılmamıştı.

Yalnız isteğin ÇIKTI olarak andığı yollar sayılır: ters tırnaklı, uzantılı bir yol ve
yakınında "olarak / olsun / kaydet / render / üret / çıktı / save / output / export".
Okunacak ya da düzeltilecek dosya ("`app.py` içindeki hatayı düzelt") çıktı değildir.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from ...core.tools import ToolContext
from ...core.verification import VerificationResult

#: Ters tırnak içindeki göreli, uzantılı yol (adres ve mutlak yol değil).
_PATH = re.compile(r"`(?P<path>(?![a-z]+://)(?!/)[\w.\-/]+\.[A-Za-z0-9]{1,5})`")
#: Yolun hemen ardında (ya da önünde) çıktı olduğunu söyleyen sözler.
_OUTPUT_WORDS = re.compile(
    r"olarak|olsun|kaydet|render|üret|uret|çıktı|cikti|dışa aktar|\bsave\b|\boutput\b|"
    r"\bexport\b|\bwrite to\b",
    re.IGNORECASE,
)
#: Yolun çevresinde bakılan pencere (karakter).
_WINDOW = 40
#: Aynı adlı dosya aranırken atlanan klasörler.
_SKIP_DIRS = frozenset({"node_modules", ".git", ".venv", "__pycache__", ".fusion"})
#: Siyahlığı ölçülen video uzantıları.
_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".mkv"})
#: Kısa geçiş kararmaları sayılmaz; bu süreden uzun siyah bölüm kusurdur (sn).
MAX_BLACK_S = 1.0
#: ffmpeg ölçümünün azami süresi (sn).
FFMPEG_TIMEOUT_S = 120.0
_BLACK = re.compile(r"black_start:(?P<s>[\d.]+)\s+black_end:(?P<e>[\d.]+)")
_DURATION = re.compile(r"Duration:\s*(?P<h>\d+):(?P<m>\d+):(?P<s>[\d.]+)")
#: Başka yerde aranan aynı adlı dosya sayısı tavanı (büyük depolarda tarama sınırlı kalır).
_MAX_SCAN = 20_000


def requested_outputs_in(task: str) -> tuple[str, ...]:
    """İsteğin çıktı olarak andığı göreli dosya yolları (sırası korunur, tekrarsız)."""
    found: list[str] = []
    for match in _PATH.finditer(task):
        around = task[max(0, match.start() - _WINDOW) : match.end() + _WINDOW]
        if _OUTPUT_WORDS.search(around) and match.group("path") not in found:
            found.append(match.group("path"))
    return tuple(found)


class OutputPathVerifier:
    """Kullanıcının istediği çıktı dosyaları kök dizinde, istenen yolda var mı?"""

    def __init__(self, context: ToolContext) -> None:
        self._context = context

    async def verify(self) -> VerificationResult:
        # Bu turda hiçbir şey yazılmadıysa (soru-cevap, inceleme) söylenecek bir şey yok.
        if not self._context.requested_outputs or not self._context.touched:
            return VerificationResult(ok=True)
        root = self._context.root
        bulgular: list[str] = []
        for yol in sorted(self._context.requested_outputs):
            path = root / yol
            if not path.exists():
                bulgular.append(_finding(root, yol))
            elif path.suffix.lower() in _VIDEO_SUFFIXES:
                bulgular.extend(await _video_findings(path, yol))
        if not bulgular:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=False,
            summary=f"istenen çıktıda {len(bulgular)} sorun",
            findings=tuple(bulgular),
        )


def _finding(root: Path, yol: str) -> str:
    baska = _same_name_elsewhere(root, Path(yol).name)
    nerede = (
        f" Aynı adlı dosya şurada üretilmiş: {', '.join(baska)} — onu istenen yola taşı "
        "ya da kopyala (ya da üretimi doğrudan istenen yola yap)."
        if baska
        else " Dosyayı istenen yolda üret."
    )
    return f"İSTENEN ÇIKTI YOK: kullanıcı `{yol}` istedi, bu yolda dosya yok.{nerede}"


def _same_name_elsewhere(root: Path, name: str) -> list[str]:
    bulunan: list[str] = []
    for sayac, path in enumerate(root.rglob(name)):
        if sayac >= _MAX_SCAN or len(bulunan) >= 3:
            break
        if path.is_file() and not _SKIP_DIRS.intersection(path.relative_to(root).parts):
            bulunan.append(path.relative_to(root).as_posix())
    return bulunan


def black_segments(ffmpeg_log: str) -> tuple[tuple[float, float], ...]:
    """ffmpeg `blackdetect` çıktısındaki siyah bölümler (başlangıç, bitiş sn)."""
    return tuple((float(m["s"]), float(m["e"])) for m in _BLACK.finditer(ffmpeg_log))


async def measure_black(path: Path) -> tuple[tuple[tuple[float, float], ...], float] | None:
    """Videodaki siyah bölümler ve toplam süre; ffmpeg yoksa ya da ölçemezse None."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    try:
        surec = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-hide_banner",
            "-i",
            str(path),
            "-vf",
            "blackdetect=d=0.1:pix_th=0.1",
            "-an",
            "-f",
            "null",
            "-",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await asyncio.wait_for(surec.communicate(), timeout=FFMPEG_TIMEOUT_S)
    except (OSError, TimeoutError):
        return None
    log = err.decode("utf-8", errors="replace")
    sure = _DURATION.search(log)
    toplam = int(sure["h"]) * 3600 + int(sure["m"]) * 60 + float(sure["s"]) if sure else 0.0
    return black_segments(log), toplam


async def _video_findings(path: Path, yol: str) -> list[str]:
    """Uzun siyah bölüm: video render edildi ama sahneler görünmüyor.

    Ölçüldü (6 Ekim 2026, dalga23 Remotion): 10 sn'lik videonun 3,8-10,0 sn arası
    tamamen siyahtı; Fusion ffprobe ile yalnız süre/çözünürlüğe baktı, kareye bakmadı.
    """
    olcum = await measure_black(path)
    if olcum is None:
        return []
    bolumler, toplam = olcum
    uzun = [(bas, son) for bas, son in bolumler if son - bas > MAX_BLACK_S]
    if not uzun:
        return []
    araliklar = ", ".join(f"{bas:.1f}-{son:.1f} sn" for bas, son in uzun)
    siyah = sum(son - bas for bas, son in uzun)
    oran = f" (toplam sürenin %{100 * siyah / toplam:.0f})" if toplam else ""
    return [
        f"VİDEO SİYAH: `{yol}` içinde {araliklar} tamamen siyah{oran}. O aralıktaki "
        "sahneler görünmüyor — Sequence içinde useCurrentFrame() sahneye GÖRE başlar; "
        "interpolate aralıklarını ve opaklığı kontrol et, o saniyelerden "
        "`npx remotion still <Id> --frame=<n>` ile kare alıp bak, düzeltip yeniden render et."
    ]

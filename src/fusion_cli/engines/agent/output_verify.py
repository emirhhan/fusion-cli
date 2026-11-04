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
import contextlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from ...core.evidence import CriterionEvidence, EvidenceStatus
from ...core.execution_plan import VerificationCheckKind
from ...core.tools import ToolContext
from ...core.verification import VerificationResult
from ...tools.remotion_bootstrap import VIDEO_FPS, VIDEO_HEIGHT, VIDEO_WIDTH
from ...tools.video_evidence import (
    ExpectedVideo,
    VideoUnreadableError,
    decode_errors,
    mismatches,
    read_video_facts,
)
from .artifact_verify import inspect_artifact
from .output_contract import (
    capture_output_baselines as capture_output_baselines,
)
from .output_contract import (
    output_file_version,
)
from .output_contract import (
    requested_outputs_in as requested_outputs_in,
)

#: Aynı adlı dosya aranırken atlanan klasörler.
_SKIP_DIRS = frozenset({"node_modules", ".git", ".venv", "__pycache__", ".fusion"})
#: Siyahlığı ölçülen video uzantıları.
_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".mkv"})
#: Kısa geçiş kararmaları sayılmaz; bu süreden uzun siyah bölüm kusurdur (sn).
MAX_BLACK_S = 1.0
#: ffmpeg ölçümünün azami süresi (sn).
FFMPEG_TIMEOUT_S = 120.0
_BLACK = re.compile(r"black_start:(?P<s>[\d.]+)\s+black_end:(?P<e>[\d.]+)")
#: Bundan uzun donuk (kıpırtısız) bölüm "slayt gösterisi" sayılır (sn). Ölçüldü (dalga24):
#: sade fade videoda 30 sn'nin ~19'u donuktu; hareket kitiyle yapılan demoda hiç yoktu.
MAX_FREEZE_S = 1.5
_DURATION = re.compile(r"Duration:\s*(?P<h>\d+):(?P<m>\d+):(?P<s>[\d.]+)")
#: Başka yerde aranan aynı adlı dosya sayısı tavanı (büyük depolarda tarama sınırlı kalır).
_MAX_SCAN = 20_000


async def _ffmpeg_stderr(ffmpeg: str, path: Path, filter_graph: str) -> bytes | None:
    """ffmpeg'i süreyle çalıştır, stderr'i döndür; zaman aşımında SÜRECİ ÖLDÜR.

    Ölçüldü (30 Ekim, A2-30): `wait_for(communicate())` zaman aşımında yalnız
    bekleyeni iptal ediyor, ffmpeg arka planda videoyu çözmeye devam ediyordu
    (siyah + donuk iki ölçüm = en kötü 240 sn, iki kez çözme).
    """
    try:
        surec = await asyncio.create_subprocess_exec(
            ffmpeg,
            "-hide_banner",
            "-i",
            str(path),
            "-vf",
            filter_graph,
            "-an",
            "-f",
            "null",
            "-",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        return None
    try:
        _, err = await asyncio.wait_for(surec.communicate(), timeout=FFMPEG_TIMEOUT_S)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            surec.kill()
        await surec.wait()
        return None
    return err


class OutputPathVerifier:
    """Kullanıcının istediği çıktı dosyaları kök dizinde, istenen yolda var mı?"""

    def __init__(self, context: ToolContext) -> None:
        self._context = context

    async def verify(self) -> VerificationResult:
        # Bu turda hiçbir şey yazılmadıysa (soru-cevap, inceleme) söylenecek bir şey yok.
        if not self._context.requested_outputs:
            return VerificationResult(ok=True)
        root = self._context.root
        bulgular: list[str] = []
        uyarilar: list[str] = []
        kanitlar: list[str] = []
        criteria: list[CriterionEvidence] = []
        for yol in sorted(self._context.requested_outputs):
            path = root / yol
            resolved = path.resolve()
            if not resolved.is_relative_to(root.resolve()):
                bulgular.append(f"ÇIKTI KAPSAM DIŞI: `{yol}` proje kökü dışına çözülüyor.")
                continue
            if not path.exists():
                bulgular.append(await _finding(root, yol))
                continue
            if yol in self._context.output_baselines:
                if output_file_version(path) == self._context.output_baselines[yol]:
                    bulgular.append(
                        f"ÇIKTI GÜNCEL DEĞİL: `{yol}` bu turda üretilmedi veya güncellenmedi."
                    )
                    continue
            elif path not in self._context.touched:
                warning = f"ÇIKTI ÖLÇÜLEMEDİ: `{yol}` dosyasının bu turda üretildiği doğrulanamadı."
                uyarilar.append(warning)
                criteria.append(
                    CriterionEvidence(
                        criterion_id=f"cikti_guncellik:{yol}",
                        kind=VerificationCheckKind.TOOL,
                        status=EvidenceStatus.UNVERIFIED,
                        artifact=yol,
                        summary=warning,
                    )
                )
            if path.suffix.lower() not in _VIDEO_SUFFIXES:
                inspection = await asyncio.to_thread(inspect_artifact, path)
                if inspection.problem:
                    bulgular.append(f"ÇIKTI GEÇERSİZ: `{yol}` {inspection.problem}")
                if inspection.warning:
                    uyarilar.append(f"ÇIKTI ÖLÇÜLEMEDİ: `{yol}` {inspection.warning}")
                criteria.append(
                    CriterionEvidence(
                        criterion_id=f"cikti:{yol}",
                        kind=VerificationCheckKind.TOOL,
                        artifact=yol,
                        summary=inspection.problem or inspection.warning or f"{yol} açıldı",
                        status=EvidenceStatus.FAILED
                        if inspection.problem
                        else (
                            EvidenceStatus.UNVERIFIED
                            if inspection.warning
                            else EvidenceStatus.PASSED
                        ),
                    )
                )
            elif path.suffix.lower() in _VIDEO_SUFFIXES:
                kanit = await _video_evidence(path, yol, self._expected_video())
                bulgular.extend(kanit.findings)
                uyarilar.extend(kanit.warnings)
                kanitlar.extend(kanit.proofs)
                if not kanit.findings:
                    bulgular.extend(
                        await _video_findings(
                            path, yol, remotion="remotion" in self._context.task_kinds
                        )
                    )
        if not bulgular:
            return VerificationResult(
                ok=True,
                summary="; ".join(kanitlar),
                warnings=tuple(uyarilar),
                evidence=tuple(criteria),
            )
        return VerificationResult(
            ok=False,
            summary=f"istenen çıktıda {len(bulgular)} sorun",
            findings=tuple(bulgular),
            warnings=tuple(uyarilar),
            evidence=tuple(criteria),
        )

    def _expected_video(self) -> ExpectedVideo | None:
        """Host Remotion planı kayıtlıysa videonun süre/çözünürlük/kare hızı beklentisi."""
        contract = self._context.remotion_contract.registered
        if contract is None or not contract.scenes:
            return None
        frames = sum(scene.duration for scene in contract.scenes)
        return ExpectedVideo(VIDEO_WIDTH, VIDEO_HEIGHT, float(VIDEO_FPS), frames / VIDEO_FPS)


@dataclass(frozen=True, slots=True)
class _VideoEvidence:
    findings: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    proofs: tuple[str, ...] = ()


async def _video_evidence(path: Path, yol: str, expected: ExpectedVideo | None) -> _VideoEvidence:
    """Gerçek dosya kanıtı: boyut > 0, ffprobe ile süre/çözünürlük, tam çözme, plan uyumu.

    Ölçüldü (29 Ekim): yalnız yolun varlığına bakılıyordu; ffprobe/ffmpeg yoksa ölçüm
    sessizce atlanıyordu. Artık araç yoksa `not_measured` uyarısı çıkar.
    """
    try:
        facts = await read_video_facts(path)
    except VideoUnreadableError as error:
        return _VideoEvidence(
            findings=(
                f"VİDEO GEÇERSİZ: `{yol}` oynatılabilir bir video değil ({error}). "
                "Render'ın bittiğini job_status ile doğrula, dosyayı yeniden üret.",
            )
        )
    if facts is None:
        return _VideoEvidence(
            warnings=(
                f"VİDEO ÖLÇÜLEMEDİ (not_measured): `{yol}` var ama ffprobe/ffmpeg kurulu "
                "olmadığı için süre, çözünürlük ve oynatılabilirlik doğrulanmadı.",
            )
        )
    bozuk = await decode_errors(path)
    if bozuk:
        return _VideoEvidence(
            findings=(f"VİDEO ÇÖZÜLEMİYOR: `{yol}` kareleri çözülürken ffmpeg hata verdi: {bozuk}",)
        )
    farklar = mismatches(facts, expected) if expected is not None else []
    if farklar:
        return _VideoEvidence(
            findings=(
                f"VİDEO PLANA UYMUYOR: `{yol}` " + "; ".join(farklar) + ". Kayıtlı kit planı "
                "1920x1080/30'dur; sahne sürelerini ve render komutunu kontrol edip yeniden "
                "render et.",
            )
        )
    return _VideoEvidence(proofs=(f"video kanıtı `{yol}`: {facts.summary()}",))


async def _finding(root: Path, yol: str) -> str:
    baska = await asyncio.to_thread(_same_name_elsewhere, root, Path(yol).name)
    nerede = (
        f" Aynı adlı dosya şurada üretilmiş: {', '.join(baska)} — onu istenen yola taşı "
        "ya da kopyala (ya da üretimi doğrudan istenen yola yap)."
        if baska
        else " Dosyayı istenen yolda üret."
    )
    return f"İSTENEN ÇIKTI YOK: kullanıcı `{yol}` istedi, bu yolda dosya yok.{nerede}"


def _same_name_elsewhere(root: Path, name: str) -> list[str]:
    """Aynı adlı dosyayı kök altında ara; `node_modules`/`.git` ağacına HİÇ inilmez.

    Ölçüldü (30 Ekim, A2-31): `root.rglob(name)` süzgeci yalnız eşleşmelere uyguluyor,
    gürültü dizinlerini yine dolaşıyordu ve olay döngüsünden senkron çağrılıyordu.
    """
    bulunan: list[str] = []
    gezilen = 0
    for dizin, alt_dizinler, dosyalar in os.walk(root):
        alt_dizinler[:] = [ad for ad in alt_dizinler if ad not in _SKIP_DIRS]
        gezilen += len(dosyalar)
        if name in dosyalar:
            bulunan.append((Path(dizin) / name).relative_to(root).as_posix())
            if len(bulunan) >= 3:
                break
        if gezilen >= _MAX_SCAN:
            break
    return bulunan


def black_segments(ffmpeg_log: str) -> tuple[tuple[float, float], ...]:
    """ffmpeg `blackdetect` çıktısındaki siyah bölümler (başlangıç, bitiş sn)."""
    return tuple((float(m["s"]), float(m["e"])) for m in _BLACK.finditer(ffmpeg_log))


async def measure_black(path: Path) -> tuple[tuple[tuple[float, float], ...], float] | None:
    """Videodaki siyah bölümler ve toplam süre; ffmpeg yoksa ya da ölçemezse None."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    err = await _ffmpeg_stderr(ffmpeg, path, "blackdetect=d=0.1:pix_th=0.1")
    if err is None:
        return None
    log = err.decode("utf-8", errors="replace")
    sure = _DURATION.search(log)
    toplam = int(sure["h"]) * 3600 + int(sure["m"]) * 60 + float(sure["s"]) if sure else 0.0
    return black_segments(log), toplam


def freeze_segments(ffmpeg_log: str, total_s: float) -> tuple[tuple[float, float], ...]:
    """ffmpeg `freezedetect` çıktısındaki donuk bölümler (bitişi yoksa video sonuna dek)."""
    bolumler: list[tuple[float, float]] = []
    for satir in ffmpeg_log.split("freeze_start:")[1:]:
        bas = float(satir.split()[0])
        son = re.search(r"freeze_end:\s*([\d.]+)", satir)
        bolumler.append((bas, float(son.group(1)) if son else total_s))
    return tuple(bolumler)


async def measure_freeze(path: Path, total_s: float) -> tuple[tuple[float, float], ...]:
    """Videodaki donuk bölümler; ffmpeg yoksa boş."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return ()
    err = await _ffmpeg_stderr(ffmpeg, path, f"freezedetect=n=0.002:d={MAX_FREEZE_S}")
    if err is None:
        return ()
    return freeze_segments(err.decode("utf-8", errors="replace"), total_s)


async def _video_findings(path: Path, yol: str, *, remotion: bool = True) -> list[str]:
    """Uzun siyah bölüm: video render edildi ama sahneler görünmüyor.

    Ölçüldü (6 Ekim 2026, dalga23 Remotion): 10 sn'lik videonun 3,8-10,0 sn arası
    tamamen siyahtı; Fusion ffprobe ile yalnız süre/çözünürlüğe baktı, kareye bakmadı.
    """
    olcum = await measure_black(path)
    if olcum is None:
        return []
    bolumler, toplam = olcum
    # Donukluk kuralı Remotion hareket kitine göre ayarlıdır (A2-32): ekran kaydı ya da
    # bilerek hareketsiz ders videosunda yanlış pozitif olurdu; yalnız Remotion görevinde.
    bulgular = await _freeze_findings(path, yol, toplam) if remotion else []
    uzun = [(bas, son) for bas, son in bolumler if son - bas > MAX_BLACK_S]
    if not uzun:
        return bulgular
    araliklar = ", ".join(f"{bas:.1f}-{son:.1f} sn" for bas, son in uzun)
    siyah = sum(son - bas for bas, son in uzun)
    oran = f" (toplam sürenin %{100 * siyah / toplam:.0f})" if toplam else ""
    return [
        *bulgular,
        f"VİDEO SİYAH: `{yol}` içinde {araliklar} tamamen siyah{oran}. O aralıktaki "
        "sahneler görünmüyor. "
        + (
            "Sequence içinde useCurrentFrame() sahneye GÖRE başlar; interpolate "
            "aralıklarını ve opaklığı kontrol et, o saniyelerden "
            "`npx remotion still <Id> --frame=<n>` ile kare alıp bak, düzeltip yeniden render et."
            if remotion
            else "O saniyelerden kare alıp bak, kaynağı düzeltip yeniden üret."
        ),
    ]


async def _freeze_findings(path: Path, yol: str, toplam: float) -> list[str]:
    """Uzun donuk bölümler: video bir slayt gösterisi gibi duruyor.

    Kullanıcı (6 Ekim 2026): "bildiğin fade in şekilde yazılar gelmiş, basit kalmış".
    """
    donuk = await measure_freeze(path, toplam)
    if not donuk:
        return []
    sure = sum(son - bas for bas, son in donuk)
    araliklar = ", ".join(f"{bas:.1f}-{son:.1f}" for bas, son in donuk[:6])
    oran = f" (toplam sürenin %{100 * sure / toplam:.0f})" if toplam else ""
    return [
        f"VİDEO DONUK: `{yol}` içinde {sure:.1f} sn hiç kıpırdamıyor{oran}: {araliklar} sn. "
        "Sahneler slayt gibi duruyor — hareket kitini kullan (Aurora + Particles zemin, "
        "CameraPush ile sar, KineticText/FeatureCard ile giriş); her an en az iki katman "
        "hareket etsin."
    ]

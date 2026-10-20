"""Arka plan işleri: uzun komutu ayrı süreçte başlat, sonra durumunu sor.

Ölçüldü: `run_shell` 120 sn'de komutu öldürüyordu; `npm install`, `npx remotion
render`, `godot --export` ve uzun WP-CLI işleri bu sınırda kesiliyor, model komutu
"başarısız" sanıyordu. Burada komut ayrı bir süreç grubunda başlar, çıktısı
`.fusion/is/<kimlik>.log` dosyasına, çıkış kodu `<kimlik>.exit` dosyasına yazılır.

Durum modül-global tutulmaz (RULES: paylaşılan araç durumu çağrı bağlamına ya da
diske bağlanır): her şey proje kökündeki iş klasöründen okunur, böylece süreç
yeniden başlasa da iş izlenebilir.
"""

from __future__ import annotations

import re
import shlex
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from threading import Thread

from ..core.atomic_file import atomic_replace_text
from ..core.constants import (
    JOB_LOG_TAIL_CHARS,
    JOB_MAX_WAIT_S,
    PROCESS_POLL_S,
    PROCESS_TERMINATE_GRACE_S,
)
from ..core.errors import CleanupFailedError
from ..core.job_evidence import ArtifactReceipt
from ..core.process_control import ensure_process_group_exit, terminate_process_tree
from ..core.repair_ledger import FailureEvidence
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_positive_int, require_str
from .job_delivery import observe_delivery, save_delivery
from .job_evidence import JobEvidenceManifest, completed_evidence, save_manifest
from .job_owner import save_owner, verified_owner
from .remotion_shell_guard import check_shell_result

#: İş dosyalarının proje köküne göre yeri.
JOBS_DIR = Path(".fusion") / "is"
_JOB_ID = re.compile(r"^[a-f0-9]{8}$")
#: Durdurulan işin çıkış kodu: kabuk geleneği 128 + SIGTERM.
_TERMINATED_EXIT = 128 + signal.SIGTERM
#: Bekleme döngüsünün yoklama aralığı (saniye).
_POLL_S = PROCESS_POLL_S


def _jobs_dir(context: ToolContext) -> Path:
    return context.root / JOBS_DIR


def _reserve_job_id(folder: Path, command: str) -> str:
    while True:
        job_id = uuid.uuid4().hex[:8]
        try:
            with (folder / f"{job_id}.cmd").open("x", encoding="utf-8") as stream:
                stream.write(command)
            return job_id
        except FileExistsError:
            continue


def start_job(
    command: str,
    context: ToolContext,
    env: dict[str, str],
    *,
    manifest: JobEvidenceManifest | None = None,
    outputs: tuple[ArtifactReceipt, ...] = (),
) -> ToolResult:
    """Komutu arka planda başlat; kimliği ve izleme yolunu döner."""
    klasor = _jobs_dir(context)
    klasor.mkdir(parents=True, exist_ok=True)
    kimlik = _reserve_job_id(klasor, command)
    gunluk = klasor / f"{kimlik}.log"
    cikis = klasor / f"{kimlik}.exit"
    if manifest is not None:
        save_manifest(klasor / f"{kimlik}.proof.json", manifest)
    delivery = save_delivery(klasor, kimlik, command, manifest, outputs)
    # Çıkış kodu kabuğun kendisi tarafından dosyaya yazılır: süreç bizden bağımsız biter.
    # Komut alt kabukta çalışır; içindeki `exit` sarmalayıcıyı da bitirip kodu yutmasın.
    receipt = Path(__file__).parent / "job_receipt.py"
    observer = " ".join(
        shlex.quote(value)
        for value in (
            sys.executable,
            str(receipt),
            str(context.root),
            kimlik,
        )
    )
    token = "fusion-job-" + uuid.uuid4().hex
    sarmal = (
        f": {token}; "
        f"( {command} ) > {shlex.quote(str(gunluk))} 2>&1; fusion_job_code=$?; "
        f'{observer} "$fusion_job_code" >> {shlex.quote(str(gunluk))} 2>&1; '
        f'echo "$fusion_job_code" > {shlex.quote(str(cikis))}'
    )
    try:
        surec = subprocess.Popen(
            sarmal,
            shell=True,
            cwd=context.root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return ToolResult.failure(f"Arka plan işi başlatılamadı: {exc}")
    Thread(target=surec.wait, name=f"fusion-job-{kimlik}", daemon=True).start()
    try:
        save_owner(klasor, kimlik, surec.pid, token, context, lambda: surec.poll() is not None)
        atomic_replace_text(klasor / f"{kimlik}.pid", str(surec.pid))
    except (OSError, ValueError, subprocess.SubprocessError):
        terminate_process_tree(surec.pid, force=True)
        try:
            surec.wait(timeout=PROCESS_TERMINATE_GRACE_S)
        except subprocess.TimeoutExpired:
            raise CleanupFailedError("Kaydı başarısız yeni işin kapanışı doğrulanamadı.") from None
        ensure_process_group_exit(surec.pid)
        return ToolResult.failure("İş sahipliği kaydedilemedi; yeni süreç kapatıldı.")
    return ToolResult(
        f"Arka plan işi başladı: {kimlik}\nKomut: {command}\nÇıktı: {gunluk}\n"
        f"Durumu ve son çıktıyı görmek için job_status(id='{kimlik}', wait_s=...) çağır; "
        "bitmesini beklemek için wait_s ver. Gerekirse job_status(id, stop=true) ile durdur.",
        job_completion=delivery,
    )


def _read_exit(klasor: Path, kimlik: str) -> int | None:
    yol = klasor / f"{kimlik}.exit"
    try:
        metin = yol.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(metin) if metin.lstrip("-").isdigit() else None


def _tail(klasor: Path, kimlik: str) -> str:
    try:
        metin = (klasor / f"{kimlik}.log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(metin) <= JOB_LOG_TAIL_CHARS:
        return metin
    return (
        f"[… ilk {len(metin) - JOB_LOG_TAIL_CHARS} karakter atlandı]\n{metin[-JOB_LOG_TAIL_CHARS:]}"
    )


def _job_id(args: ToolArgs, context: ToolContext) -> tuple[str, Path] | ToolResult:
    kimlik = require_str(args, "id").strip()
    klasor = _jobs_dir(context)
    if not _JOB_ID.match(kimlik) or not (klasor / f"{kimlik}.cmd").is_file():
        bilinen = sorted(p.stem for p in klasor.glob("*.cmd")) if klasor.is_dir() else []
        return ToolResult.failure(
            f"'{kimlik}' adlı arka plan işi yok. Bilinen işler: {', '.join(bilinen) or 'yok'}."
        )
    return kimlik, klasor


def job_status(args: ToolArgs, context: ToolContext) -> ToolResult:
    """İşin durumunu ver; `wait_s` kadar (en çok JOB_MAX_WAIT_S) bitmesini bekle."""
    cozum = _job_id(args, context)
    if isinstance(cozum, ToolResult):
        return cozum
    kimlik, klasor = cozum
    if args.get("stop") is True:
        return _stop(kimlik, klasor, context)
    bekle = min(require_positive_int(args, "wait_s", default=1), int(JOB_MAX_WAIT_S))
    bitis = time.monotonic() + bekle
    kod = _read_exit(klasor, kimlik)
    while kod is None and time.monotonic() < bitis and not context.cancelled.is_set():
        time.sleep(_POLL_S)
        kod = _read_exit(klasor, kimlik)
    cikti = _tail(klasor, kimlik)
    try:
        delivery = observe_delivery(klasor, context.root, kimlik, kod)
    except (OSError, ValueError) as error:
        return ToolResult.failure(f"İş teslim kanıtı okunamadı: {error}")
    if kod is None:
        return ToolResult(
            f"İş {kimlik} SÜRÜYOR ({bekle} sn beklendi).\n[son çıktı]\n{cikti}",
            is_observation=True,
            job_completion=delivery,
        )
    evidence: tuple[FailureEvidence, ...] = ()
    warning = ""
    if kod != 0:
        try:
            evidence = completed_evidence(klasor, kimlik)
        except (OSError, ValueError) as error:
            warning = f"\nYapılandırılmış kontrol kanıtı okunamadı: {error}"
    return check_shell_result(
        context,
        ToolResult(
            f"İş {kimlik} BİTTİ (çıkış kodu {kod}).\n[son çıktı]\n{cikti}{warning}",
            ok=kod == 0,
            failure_evidence=evidence,
            is_observation=True,
            job_completion=delivery,
        ),
    )


def _stop(kimlik: str, klasor: Path, context: ToolContext) -> ToolResult:
    """Doğrulanmış owner'ın süreç grubunu kapat; sinyal teslimini bitiş sayma."""
    if _read_exit(klasor, kimlik) is not None:
        return ToolResult(f"İş {kimlik} zaten bitmiş.")
    try:
        pid = verified_owner(klasor, kimlik, context)
        terminate_process_tree(pid, force=False)
        ensure_process_group_exit(pid, graceful=True)
    except (OSError, ValueError, CleanupFailedError, subprocess.SubprocessError) as exc:
        return ToolResult.failure(f"İş {kimlik} durdurulamadı: {exc}")
    atomic_replace_text(klasor / f"{kimlik}.exit", str(_TERMINATED_EXIT))
    return ToolResult(f"İş {kimlik} durduruldu.")

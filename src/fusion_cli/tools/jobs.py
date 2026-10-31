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

import json
import logging
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Thread

from ..core.atomic_file import atomic_replace_text
from ..core.constants import (
    JOB_LOG_TAIL_CHARS,
    JOB_MAX_WAIT_S,
    JOB_RECEIPT_GRACE_S,
    PROCESS_POLL_S,
    PROCESS_TERMINATE_GRACE_S,
)
from ..core.errors import CleanupFailedError
from ..core.job_evidence import ArtifactReceipt
from ..core.process_control import ensure_process_group_exit, terminate_process_tree
from ..core.repair_ledger import FailureEvidence
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_positive_int, require_str
from .job_delivery import observe_delivery, save_completion, save_delivery
from .job_evidence import JobEvidenceManifest, completed_evidence, save_manifest
from .job_owner import process_identity, save_owner, verified_owner
from .remotion_shell_guard import check_shell_result

_LOG = logging.getLogger(__name__)

#: İş dosyalarının proje köküne göre yeri.
JOBS_DIR = Path(".fusion") / "is"
_JOB_ID = re.compile(r"^[a-f0-9]{8}$")
#: Durdurulan işin çıkış kodu: kabuk geleneği 128 + SIGTERM.
_TERMINATED_EXIT = 128 + signal.SIGTERM
#: Bekleme döngüsünün yoklama aralığı (saniye).
_POLL_S = PROCESS_POLL_S
#: Sarmalayıcının hâlâ yaşadığının yoklanma aralığı (saniye); `ps` her turda çağrılmaz.
_LIVENESS_CHECK_S = 1.0


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
    argv_prefix: tuple[str, ...] = (),
    on_exit: Callable[[], str] | None = None,
) -> ToolResult:
    """Komutu arka planda başlat; kimliği ve izleme yolunu döner.

    `argv_prefix` (ör. `sandbox-exec ...`) YALNIZ kullanıcı komutunu sarar; günlük
    yönlendirmesi ve çıkış makbuzu sandbox'ın dışında kalır. `on_exit` sarmalayıcı
    bitince izleyici iş parçacığında çağrılır (işin sahip olduğu kaynakları kapatır, ör.
    sandbox proxy'si); döndürdüğü metin günlüğün sonuna eklenir. Süreç hiç başlamazsa
    çağrılmaz: kaynağı çağıran kapatır.
    """
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
    # Dondurulmuş (PyInstaller/Tauri sidecar) uygulamada `sys.executable` yorumlayıcı değil
    # uygulamanın kendisidir ve `job_receipt.py` çalışmaz (T2-37): makbuz o zaman sarmalayıcıda
    # değil, işi izleyen host iş parçacığında yazılır. Kaynak kurulumunda sarmalayıcı yolu
    # sürer: makbuz host kapalıyken biten işte de yazılır.
    host_writes_receipt = bool(getattr(sys, "frozen", False))
    receipt_step = "" if host_writes_receipt else _receipt_command(context, kimlik, gunluk)
    token = "fusion-job-" + uuid.uuid4().hex
    # Komut düz metin gömülmez, kendi dosyasından (`<kimlik>.cmd`) çalıştırılır.
    # Ölçüldü (29 Ekim): `( komut )` içine gömülen `npm test # not` kapanış
    # parantezini yorum satırına alıyor, dengesiz tırnak sarmalayıcıyı sözdizimi
    # hatasıyla düşürüyordu; `.exit` hiç yazılmıyor, iş sonsuza dek SÜRÜYOR görünüyordu.
    komut_dosyasi = klasor / f"{kimlik}.cmd"
    sarmal = (
        f": {token}; "
        f"( {_command_argv(argv_prefix, komut_dosyasi)} ) > {shlex.quote(str(gunluk))} 2>&1; "
        "fusion_job_code=$?; "
        f"{receipt_step}"
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
    Thread(
        target=_watch_job,
        args=(surec, klasor, context.root, kimlik, host_writes_receipt, on_exit),
        name=f"fusion-job-{kimlik}",
        daemon=True,
    ).start()
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


def _command_argv(argv_prefix: tuple[str, ...], komut_dosyasi: Path) -> str:
    return shlex.join([*argv_prefix, "sh", str(komut_dosyasi)])


def _receipt_command(context: ToolContext, kimlik: str, gunluk: Path) -> str:
    """Sarmalayıcıda makbuzu yazan komut parçası (kaynak kurulumu)."""
    receipt = Path(__file__).parent / "job_receipt.py"
    observer = " ".join(
        shlex.quote(value) for value in (sys.executable, str(receipt), str(context.root), kimlik)
    )
    return f'{observer} "$fusion_job_code" >> {shlex.quote(str(gunluk))} 2>&1; '


def _watch_job(
    surec: subprocess.Popen[bytes],
    klasor: Path,
    root: Path,
    kimlik: str,
    host_writes_receipt: bool,
    on_exit: Callable[[], str] | None = None,
) -> None:
    """Sarmalayıcıyı bekle (zombi kalmasın); dondurulmuş uygulamada makbuzu burada yaz.

    Makbuz, sarmalayıcının `.exit` yazmasından hemen SONRA, bu iş parçacığının ilk
    işidir; `job_status` kısa bir süre makbuzu bekler (`_await_receipt`). Host bu arada
    kapanırsa makbuz yazılmaz ve teslim kanıtı isteyen iş "kanıt yok" diye REDDEDİLİR
    (başarı sayılmaz; `observe_delivery`).
    """
    surec.wait()
    if on_exit is not None:
        _finish_owned(on_exit, klasor / f"{kimlik}.log", kimlik)
    if not host_writes_receipt:
        return
    code = _read_exit(klasor, kimlik)
    if code is None:
        _LOG.warning("İş çıkış kodu okunamadı; makbuz yazılmadı", extra={"is": kimlik})
        return
    try:
        save_completion(klasor, root, kimlik, code)
    except (OSError, ValueError):
        _LOG.exception("İş tamamlanma makbuzu host süreçte yazılamadı", extra={"is": kimlik})


def _finish_owned(on_exit: Callable[[], str], gunluk: Path, kimlik: str) -> None:
    """İşin kaynaklarını kapat; notu günlüğe ekle. Hata izleyiciyi düşürmez, log'lanır."""
    try:
        note = on_exit()
        if note:
            with gunluk.open("a", encoding="utf-8") as stream:
                stream.write(note)
    except (OSError, ValueError):
        _LOG.exception("Arka plan işinin kaynakları kapatılamadı", extra={"is": kimlik})


def _await_receipt(klasor: Path, kimlik: str) -> None:
    """Bitmiş işin makbuzu henüz yazılmadıysa kısa süre bekle (host yazıcı yarışı)."""
    if not (klasor / f"{kimlik}.delivery.json").exists():
        return
    bitis = time.monotonic() + JOB_RECEIPT_GRACE_S
    while not (klasor / f"{kimlik}.receipt.json").exists() and time.monotonic() < bitis:
        time.sleep(_POLL_S)


def _read_exit(klasor: Path, kimlik: str) -> int | None:
    yol = klasor / f"{kimlik}.exit"
    try:
        metin = yol.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return int(metin) if metin.lstrip("-").isdigit() else None


def _wrapper_gone(klasor: Path, kimlik: str) -> bool:
    """İşin sarmalayıcı kabuğu artık yok mu? Doğrulanamıyorsa False (sürüyor say).

    Sahiplik kaydı (`.owner.json` + `.pid`) süreç başlangıç kimliğini taşır: PID
    başka bir sürece geçmişse de, süreç yoksa da kimlik doğrulanamaz.
    """
    try:
        owner = json.loads((klasor / f"{kimlik}.owner.json").read_text(encoding="utf-8"))
        pid = int((klasor / f"{kimlik}.pid").read_text(encoding="utf-8"))
        token = owner["token"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if not isinstance(token, str) or not token:
        return False
    try:
        process_identity(pid, token)
    except ValueError:
        return True
    except (OSError, subprocess.SubprocessError):
        return False
    return False


def _tail(klasor: Path, kimlik: str) -> str:
    """Günlüğün SON `JOB_LOG_TAIL_CHARS` karakteri; dosyanın sonuna `seek` ile okunur.

    Eskiden `read_text` tüm günlüğü okuyup kesiyordu: sonsuz çıktı üreten bir iş
    (dev sunucusu, döngü) GB'lara çıkınca her `job_status` yoklaması bellek ve süre
    patlatıyordu (ölçüldü, 30 Ekim). UTF-8'de bir karakter en çok 4 bayttır.
    """
    yol = klasor / f"{kimlik}.log"
    try:
        with yol.open("rb") as dosya:
            boyut = dosya.seek(0, os.SEEK_END)
            okunacak = min(boyut, JOB_LOG_TAIL_CHARS * 4)
            dosya.seek(boyut - okunacak)
            ham = dosya.read(okunacak)
    except OSError:
        return ""
    metin = ham.decode("utf-8", errors="replace")
    if boyut == okunacak and len(metin) <= JOB_LOG_TAIL_CHARS:
        return metin
    kuyruk = metin[-JOB_LOG_TAIL_CHARS:]
    atlanan = boyut - len(kuyruk.encode("utf-8"))
    return f"[… ilk ~{atlanan} karakter atlandı]\n{kuyruk}"


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
    sonraki_yoklama = time.monotonic() + _LIVENESS_CHECK_S
    olu = False
    while kod is None and time.monotonic() < bitis and not context.cancelled.is_set():
        time.sleep(_POLL_S)
        kod = _read_exit(klasor, kimlik)
        if kod is None and time.monotonic() >= sonraki_yoklama:
            olu = _wrapper_gone(klasor, kimlik)
            if olu:
                kod = _read_exit(klasor, kimlik)  # son anda yazılmış olabilir
                break
            sonraki_yoklama = time.monotonic() + _LIVENESS_CHECK_S
    cikti = _tail(klasor, kimlik)
    if kod is None and (olu or _wrapper_gone(klasor, kimlik)):
        kod = _read_exit(klasor, kimlik)
        if kod is None:
            return ToolResult.failure(
                f"İş {kimlik} SONLANDI ama çıkış kodu bilinmiyor: sarmalayıcı süreç yok "
                "(öldürüldü ya da makine yeniden başladı), `.exit` yazılmadı. İşi "
                f"yeniden başlat.\n[son çıktı]\n{cikti}"
            )
    if kod is not None:
        _await_receipt(klasor, kimlik)
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

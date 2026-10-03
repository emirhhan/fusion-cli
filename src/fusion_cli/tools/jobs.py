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

import os
import re
import shlex
import signal
import subprocess
import time
import uuid
from pathlib import Path

from ..core.constants import JOB_LOG_TAIL_CHARS, JOB_MAX_WAIT_S
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_positive_int, require_str

#: İş dosyalarının proje köküne göre yeri.
JOBS_DIR = Path(".fusion") / "is"
_JOB_ID = re.compile(r"^[a-f0-9]{8}$")
#: Durdurulan işin çıkış kodu: kabuk geleneği 128 + SIGTERM.
_TERMINATED_EXIT = 128 + signal.SIGTERM
#: Bekleme döngüsünün yoklama aralığı (saniye).
_POLL_S = 1.0


def _jobs_dir(context: ToolContext) -> Path:
    return context.root / JOBS_DIR


def start_job(command: str, context: ToolContext, env: dict[str, str]) -> ToolResult:
    """Komutu arka planda başlat; kimliği ve izleme yolunu döner."""
    klasor = _jobs_dir(context)
    klasor.mkdir(parents=True, exist_ok=True)
    kimlik = uuid.uuid4().hex[:8]
    gunluk = klasor / f"{kimlik}.log"
    cikis = klasor / f"{kimlik}.exit"
    # Çıkış kodu kabuğun kendisi tarafından dosyaya yazılır: süreç bizden bağımsız biter.
    # Komut alt kabukta çalışır; içindeki `exit` sarmalayıcıyı da bitirip kodu yutmasın.
    sarmal = f"( {command} ) > {shlex.quote(str(gunluk))} 2>&1; echo $? > {shlex.quote(str(cikis))}"
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
    (klasor / f"{kimlik}.pid").write_text(str(surec.pid), encoding="utf-8")
    (klasor / f"{kimlik}.cmd").write_text(command, encoding="utf-8")
    return ToolResult(
        f"Arka plan işi başladı: {kimlik}\nKomut: {command}\nÇıktı: {gunluk}\n"
        f"Durumu ve son çıktıyı görmek için job_status(id='{kimlik}', wait_s=...) çağır; "
        "bitmesini beklemek için wait_s ver. Gerekirse job_status(id, stop=true) ile durdur."
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
        return _stop(kimlik, klasor)
    bekle = min(require_positive_int(args, "wait_s", default=1), int(JOB_MAX_WAIT_S))
    bitis = time.monotonic() + bekle
    kod = _read_exit(klasor, kimlik)
    while kod is None and time.monotonic() < bitis and not context.cancelled.is_set():
        time.sleep(_POLL_S)
        kod = _read_exit(klasor, kimlik)
    cikti = _tail(klasor, kimlik)
    if kod is None:
        return ToolResult(f"İş {kimlik} SÜRÜYOR ({bekle} sn beklendi).\n[son çıktı]\n{cikti}")
    return ToolResult(f"İş {kimlik} BİTTİ (çıkış kodu {kod}).\n[son çıktı]\n{cikti}", ok=kod == 0)


def _stop(kimlik: str, klasor: Path) -> ToolResult:
    """İşin süreç grubunu durdur."""
    if _read_exit(klasor, kimlik) is not None:
        return ToolResult(f"İş {kimlik} zaten bitmiş.")
    try:
        pid = int((klasor / f"{kimlik}.pid").read_text(encoding="utf-8"))
        os.killpg(pid, signal.SIGTERM)
    except (OSError, ValueError) as exc:
        return ToolResult.failure(f"İş {kimlik} durdurulamadı: {exc}")
    # Sarmalayıcı kabuk da durdurulduğu için çıkış kodunu o yazamaz; SIGTERM kodu yazılır.
    (klasor / f"{kimlik}.exit").write_text(str(_TERMINATED_EXIT), encoding="utf-8")
    return ToolResult(f"İş {kimlik} durduruldu.")

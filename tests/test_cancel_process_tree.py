"""İptal, inatçı torun süreçlerde de son sürede biter ve geride süreç bırakmaz (WP07).

Ölçüldü (29 Ekim, macOS):
- `setsid` ile gruptan kaçan torun stdout'u açık tutuyordu. İptal 2,5 sn'de
  `CleanupFailedError` ile bitiyor ama torun yaşamaya devam ediyordu; çıktı borusu da
  onun elinde kalıyordu.
- Grup yalnız zombilerden oluşunca macOS `killpg` için EPERM döndürüyor; bu
  "süreç ağacı temizlenemedi" diye raporlanıyordu.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

from fusion_cli.core.errors import ProcessCancelledError
from fusion_cli.core.process_control import run_foreground

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX süreç grubu")

_SINIR_S = 6.0


def _yasiyor(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _bekle_dosya(path: Path) -> int:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return int(path.read_text())
        time.sleep(0.05)
    raise AssertionError("torun başlamadı")


def _iptal_et(command: str, pid_file: Path) -> tuple[float, int]:
    cancelled = threading.Event()
    sonuc: dict[str, object] = {}

    def calistir() -> None:
        started = time.monotonic()
        try:
            run_foreground(
                command,
                cwd=pid_file.parent,
                env=dict(os.environ),
                cancelled=cancelled,
                timeout_s=60,
            )
        except BaseException as error:
            sonuc["hata"] = error
        sonuc["sure"] = time.monotonic() - started

    thread = threading.Thread(target=calistir)
    thread.start()
    torun = _bekle_dosya(pid_file)
    cancelled.set()
    thread.join(timeout=30)
    assert not thread.is_alive(), "iptal sınırsız bekledi"
    assert isinstance(sonuc.get("hata"), ProcessCancelledError), sonuc.get("hata")
    return float(sonuc["sure"]), torun  # type: ignore[arg-type]


def test_gruptan_kacan_torun_stdout_acikken_iptal_edilir(tmp_path):
    pid_file = tmp_path / "torun.pid"
    script = (
        f"import os,time; os.setsid(); open({str(pid_file)!r},'w').write(str(os.getpid())); "
        "time.sleep(60)"
    )
    command = f'{sys.executable} -c "{script}" & sleep 60'

    sure, torun = _iptal_et(command, pid_file)

    assert sure < _SINIR_S
    time.sleep(0.2)
    assert not _yasiyor(torun), "gruptan kaçan torun yaşıyor"


def test_term_yok_sayan_torun_son_surede_kapanir(tmp_path):
    pid_file = tmp_path / "torun.pid"
    command = f"sh -c 'trap \"\" TERM; echo $$ > {pid_file}; while :; do sleep 1; done' & sleep 60"

    sure, torun = _iptal_et(command, pid_file)

    assert sure < _SINIR_S
    assert not _yasiyor(torun)


def test_gruptan_kacip_term_yok_sayan_torun_da_kapanir(tmp_path):
    """Kaçan torun ikinci turda bulunamaz (ebeveyni init olur); ilk turda kapanmalı."""
    pid_file = tmp_path / "torun.pid"
    script = (
        "import os,signal,time; os.setsid(); signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"open({str(pid_file)!r},'w').write(str(os.getpid())); time.sleep(60)"
    )
    command = f'{sys.executable} -c "{script}" & sleep 60'

    sure, torun = _iptal_et(command, pid_file)

    assert sure < _SINIR_S
    assert not _yasiyor(torun), "TERM'i yok sayan kaçak torun yaşıyor"

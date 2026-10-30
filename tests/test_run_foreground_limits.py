"""Ön plan komutu: çıktı belleği sınırlı, arka plan çocuğu boruyu tutsa da dönüş gecikmez (C1-16).

Ölçüldü (30 Ekim): `communicate()` tüm çıktıyı belleğe alıyordu (60 MB çıktıda dönen metin 60 MB,
süreç belleği ≈ +276 MB). `sleep 4 &` gibi boruyu tutan arka plan çocuğu kabuk çıktıktan sonra
4 sn (sunucu olsaydı 120 sn zaman aşımı) bekletiyordu. Boruyu YÖNLENDİREN `cmd > log &` çocuğu
zaten anında dönüyor ve yaşamaya devam ediyordu; bu davranış korunur.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from pathlib import Path
from threading import Event

import pytest

from fusion_cli.core.constants import SHELL_CAPTURE_CHARS
from fusion_cli.core.process_control import run_foreground


def _run(command: str, cwd: Path, timeout_s: float = 30):
    return run_foreground(
        command, cwd=cwd, env=dict(os.environ), cancelled=Event(), timeout_s=timeout_s
    )


def test_cikti_ust_siniri_asinca_bas_ve_son_korunur_ortasi_atilir(tmp_path):
    komut = "printf 'BASLA'; head -c 3000000 /dev/zero | tr '\\0' x; printf 'SON'"

    sonuc = _run(komut, tmp_path)

    assert sonuc.returncode == 0
    assert len(sonuc.stdout) < 2 * SHELL_CAPTURE_CHARS + 500
    assert sonuc.stdout.startswith("BASLA") and sonuc.stdout.endswith("SON")
    assert "atıldı" in sonuc.stdout


def test_sinirin_altindaki_cikti_aynen_doner_stderr_ayri(tmp_path):
    sonuc = _run("echo merhaba; echo hata >&2; exit 3", tmp_path)

    assert (sonuc.stdout, sonuc.stderr, sonuc.returncode) == ("merhaba\n", "hata\n", 3)


def test_satir_sonlari_eski_metin_kipi_gibi_normallesir(tmp_path):
    assert _run("printf 'a\\r\\nb\\rc'", tmp_path).stdout == "a\nb\nc"


def test_gecersiz_utf8_cokertmez(tmp_path):
    assert "�" in _run("printf 'a\\377b'", tmp_path).stdout


def test_boruyu_tutan_arka_plan_cocugu_donusu_geciktirmez_ve_yasar(tmp_path):
    baslangic = time.monotonic()
    sonuc = _run("sleep 25 & echo pid=$!; echo selam", tmp_path, timeout_s=60)
    sure = time.monotonic() - baslangic
    pid = int(sonuc.stdout.split("pid=")[1].split()[0])
    try:
        assert sure < 8, f"kabuk çıktı ama {sure:.1f} sn bekledi"
        assert sonuc.returncode == 0 and "selam" in sonuc.stdout
        os.kill(pid, 0)  # çocuk yaşıyor: `cmd &` davranışı bozulmadı
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def test_yonlendirilmis_arka_plan_cocugu_anında_doner_ve_yasar(tmp_path):
    baslangic = time.monotonic()
    sonuc = _run("sleep 25 >/dev/null 2>&1 & echo pid=$!", tmp_path, timeout_s=60)
    pid = int(sonuc.stdout.split("pid=")[1].split()[0])
    try:
        assert time.monotonic() - baslangic < 3
        os.kill(pid, 0)
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def test_zaman_asiminda_o_ana_kadarki_cikti_korunur(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired) as hata:
        _run("echo yarim; sleep 30", tmp_path, timeout_s=2)

    assert "yarim" in (hata.value.output or "")


def test_yakalayici_bas_ve_son_kesiti_tam_tutar(tmp_path):
    import io

    from fusion_cli.core.bounded_capture import BoundedCapture

    veri = bytes(range(65, 91)) * 40  # A-Z tekrarı, 1040 bayt
    yakalayici = BoundedCapture(io.BufferedReader(io.BytesIO(veri)), limit=10)
    assert yakalayici.wait_eof(5)

    metin = yakalayici.text()

    assert metin.startswith(veri[:10].decode())
    assert metin.endswith(veri[-10:].decode())
    assert f"{len(veri) - 20} bayt atıldı" in metin

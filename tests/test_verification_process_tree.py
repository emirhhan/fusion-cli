"""Doğrulama kapısı ve playbook koşucusu süreç AĞACINI temizler, okumayı sınırlar.

Ölçüldü (29 Ekim, macOS): `CommandVerifier._run` yalnız `process.wait()`'i zaman
sınırına alıyordu ve zaman aşımında yalnız kabuğu (`process.kill()`) öldürüyordu.
- Arka plana süreç doğuran komut (`dev server &`) stdout borusunu açık tutunca kabuk
  çıksa da `await okuyucu` sınırsız bekliyordu: tur "doğrulanıyor"da kalıyordu.
- Zaman aşımında/iptalde `npm → node → tsc` torunları yetim kalıyordu; iptal
  (`CancelledError`) yolunda hiç öldürme yoktu.
- `playbook.library.ShellStepRunner` aynı kalıbı kullanıyordu.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from fusion_cli.engines.agent.verification import CommandVerifier
from fusion_cli.engines.playbook.library import ShellStepRunner

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX süreç grubu")


def _yasiyor(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _olmesini_bekle(pid: int, saniye: float = 5.0) -> bool:
    bitis = time.monotonic() + saniye
    while time.monotonic() < bitis:
        if not _yasiyor(pid):
            return True
        await asyncio.sleep(0.05)
    return not _yasiyor(pid)


async def _pid_oku(dosya: Path) -> int:
    bitis = time.monotonic() + 5
    while time.monotonic() < bitis:
        if dosya.exists() and dosya.read_text().strip():
            return int(dosya.read_text())
        await asyncio.sleep(0.05)
    raise AssertionError("torun başlamadı")


def _torunlu_komut(pid_dosyasi: Path, ardindan: str) -> str:
    return f"sleep 300 & echo $! > {pid_dosyasi}; {ardindan}"


async def test_zaman_asiminda_torun_surec_de_oldurulur(tmp_path):
    pid_dosyasi = tmp_path / "torun.pid"
    kapi = CommandVerifier(
        (_torunlu_komut(pid_dosyasi, "sleep 300"),), cwd=str(tmp_path), timeout_s=1.5
    )

    sonuc = await asyncio.wait_for(kapi.verify(), timeout=20)

    assert sonuc.ok is False
    assert "zaman aşımı" in " ".join(sonuc.findings)
    assert await _olmesini_bekle(await _pid_oku(pid_dosyasi)), "torun sızdı"


async def test_arka_plan_cocugu_borusu_acik_tutsa_da_kapi_takilmaz(tmp_path):
    """Kabuk çıktı ama arka plan çocuğu stdout'u açık tutuyor: kapı sınırsız beklememeli."""
    pid_dosyasi = tmp_path / "torun.pid"
    kapi = CommandVerifier(
        (_torunlu_komut(pid_dosyasi, "echo bitti"),), cwd=str(tmp_path), timeout_s=60
    )

    baslangic = time.monotonic()
    sonuc = await asyncio.wait_for(kapi.verify(), timeout=15)

    assert time.monotonic() - baslangic < 12
    assert sonuc.ok is True
    assert await _olmesini_bekle(await _pid_oku(pid_dosyasi)), "arka plan çocuğu sızdı"


async def test_iptalde_surec_agaci_oldurulur(tmp_path):
    pid_dosyasi = tmp_path / "torun.pid"
    kapi = CommandVerifier(
        (_torunlu_komut(pid_dosyasi, "sleep 300"),), cwd=str(tmp_path), timeout_s=120
    )

    gorev = asyncio.ensure_future(kapi.verify())
    torun = await _pid_oku(pid_dosyasi)
    gorev.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(gorev, timeout=20)

    assert await _olmesini_bekle(torun), "iptalde torun sızdı"


async def test_playbook_kosucusu_zaman_asiminda_torunu_oldurur(tmp_path):
    pid_dosyasi = tmp_path / "torun.pid"
    kosucu = ShellStepRunner(cwd=str(tmp_path), timeout_s=1.5)

    kod = await asyncio.wait_for(kosucu.run(_torunlu_komut(pid_dosyasi, "sleep 300")), timeout=20)

    assert kod == 1
    assert await _olmesini_bekle(await _pid_oku(pid_dosyasi)), "torun sızdı"

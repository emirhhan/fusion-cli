"""Arka plan işleri: 120 sn'lik ön plan sınırına takılan uzun komutlar için."""

from __future__ import annotations

import os
import time

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import jobs, shell


def _bekle(context: ToolContext, kimlik: str, wait_s: int = 10) -> str:
    return jobs.job_status({"id": kimlik, "wait_s": wait_s}, context).output


def _kimlik(cikti: str) -> str:
    return cikti.split("Arka plan işi başladı: ", 1)[1].split()[0]


def test_arka_plan_isi_biter_cikis_kodu_ve_cikti_okunur(tmp_path):
    context = ToolContext(root=tmp_path)

    basla = shell.run_shell({"command": "echo merhaba; exit 3", "background": True}, context)
    kimlik = _kimlik(basla.output)
    durum = jobs.job_status({"id": kimlik, "wait_s": 10}, context)

    assert "BİTTİ (çıkış kodu 3)" in durum.output and "merhaba" in durum.output
    assert durum.ok is False


def test_suren_is_surüyor_der_ve_durdurulabilir(tmp_path):
    context = ToolContext(root=tmp_path)
    kimlik = _kimlik(shell.run_shell({"command": "sleep 30", "background": True}, context).output)

    assert "SÜRÜYOR" in jobs.job_status({"id": kimlik, "wait_s": 1}, context).output
    durdur = jobs.job_status({"id": kimlik, "stop": True}, context)

    assert "durduruldu" in durdur.output
    assert "BİTTİ" in _bekle(context, kimlik)


def test_bilinmeyen_is_kimligi_bilinenleri_listeler(tmp_path):
    context = ToolContext(root=tmp_path)
    kimlik = _kimlik(shell.run_shell({"command": "true", "background": True}, context).output)

    sonuc = jobs.job_status({"id": "../../etc"}, context)

    assert not sonuc.ok and kimlik in sonuc.output


def test_bekleme_ust_siniri_ve_iptal_beklemeyi_keser(tmp_path):
    context = ToolContext(root=tmp_path)
    kimlik = _kimlik(shell.run_shell({"command": "sleep 30", "background": True}, context).output)
    context.cancelled.set()

    basla = time.monotonic()
    jobs.job_status({"id": kimlik, "wait_s": 10_000}, context)

    assert time.monotonic() - basla < 5
    pid = int((tmp_path / jobs.JOBS_DIR / f"{kimlik}.pid").read_text(encoding="utf-8"))
    os.killpg(pid, 15)


def test_uzun_ciktinin_yalniz_sonu_gosterilir(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOB_LOG_TAIL_CHARS", 50)
    context = ToolContext(root=tmp_path)
    komut = "python3 -c \"print('a'*500 + 'SON')\""
    kimlik = _kimlik(shell.run_shell({"command": komut, "background": True}, context).output)

    cikti = _bekle(context, kimlik)

    assert "SON" in cikti and "karakter atlandı" in cikti

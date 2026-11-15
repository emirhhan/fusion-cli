"""Arka plan işleri: 120 sn'lik ön plan sınırına takılan uzun komutlar için."""

from __future__ import annotations

import os
import sys
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


# --------------------------------------------------------------------------- #
# T2-06: sarmalayıcı ve ölü süreç
# --------------------------------------------------------------------------- #


def test_yorumlu_komut_sarmalayiciyi_bozmaz(tmp_path):
    """Ölçüldü (29 Ekim): `( komut # not )` kapanış parantezini yorum satırına alıyordu."""
    context = ToolContext(root=tmp_path)
    kimlik = _kimlik(
        shell.run_shell({"command": "echo merhaba # not", "background": True}, context).output
    )

    durum = jobs.job_status({"id": kimlik, "wait_s": 10}, context)

    assert "BİTTİ (çıkış kodu 0)" in durum.output and "merhaba" in durum.output


def test_dengesiz_tirnakli_komut_bitti_der_surüyor_demez(tmp_path):
    context = ToolContext(root=tmp_path)
    kimlik = _kimlik(
        shell.run_shell({"command": 'echo "kapanmayan', "background": True}, context).output
    )

    durum = jobs.job_status({"id": kimlik, "wait_s": 10}, context)

    assert "SÜRÜYOR" not in durum.output
    assert "BİTTİ" in durum.output and durum.ok is False


def test_sarmalayici_oldurulunce_is_surüyor_gorunmez(tmp_path):
    """Ölçüldü (29 Ekim): SIGKILL ile ölen sarmalayıcı `.exit` yazamaz; iş sonsuza dek SÜRÜYOR."""
    import signal

    context = ToolContext(root=tmp_path)
    kimlik = _kimlik(shell.run_shell({"command": "sleep 60", "background": True}, context).output)
    pid = int((tmp_path / jobs.JOBS_DIR / f"{kimlik}.pid").read_text(encoding="utf-8"))
    os.killpg(pid, signal.SIGKILL)
    time.sleep(0.3)

    durum = jobs.job_status({"id": kimlik, "wait_s": 3}, context)

    assert "SONLANDI" in durum.output and "SÜRÜYOR" not in durum.output
    assert durum.ok is False


# T2-37 — Ölçüldü (30 Ekim): makbuz sarmalayıcıda `sys.executable job_receipt.py` ile yazılıyordu.
# PyInstaller/Tauri sidecar gibi dondurulmuş ikilide `sys.executable` yorumlayıcı değil uygulamanın
# kendisidir; betik çalışmaz, hata günlüğe `>>` yazılır ama `.exit` yine yazılır (iş bitmiş görünür,
# teslim kanıtı yoktur). Dondurulmuş uygulamada makbuz host süreç içinde yazılır.
def _donmus_uygulama(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # Betik çalıştırılırsa yorumlayıcı yerine bu çağrı başarısız olsun: sarmalayıcıda kalmamalı.
    monkeypatch.setattr(sys, "executable", "/yok/fusion-sidecar")


def test_donmus_uygulamada_sarmalayici_yorumlayici_cagirmaz_makbuzu_host_yazar(
    tmp_path, monkeypatch
):
    _donmus_uygulama(monkeypatch)
    context = ToolContext(root=tmp_path)
    basladi = shell.run_shell(
        {"command": "echo new > out.txt", "background": True, "expected_outputs": ["out.txt"]},
        context,
    )
    kimlik = basladi.job_completion.job_id

    sonuc = jobs.job_status({"id": kimlik, "wait_s": 10}, context)

    sarmal = (tmp_path / jobs.JOBS_DIR / f"{kimlik}.cmd").parent
    assert "/yok/fusion-sidecar" not in " ".join(
        path.read_text(errors="ignore") for path in sarmal.glob(f"{kimlik}.log")
    )
    assert sonuc.job_completion.exit_code == 0
    assert sonuc.job_completion.outputs[0].is_refreshed
    assert (sarmal / f"{kimlik}.receipt.json").is_file()


def test_donmus_uygulamada_basarisiz_is_de_makbuzla_biter(tmp_path, monkeypatch):
    _donmus_uygulama(monkeypatch)
    context = ToolContext(root=tmp_path)
    basladi = shell.run_shell(
        {"command": "exit 3", "background": True, "expected_outputs": ["out.txt"]}, context
    )

    sonuc = jobs.job_status({"id": basladi.job_completion.job_id, "wait_s": 10}, context)

    assert sonuc.job_completion.exit_code == 3

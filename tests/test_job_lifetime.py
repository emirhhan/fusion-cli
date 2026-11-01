"""Arka plan işi ömrü: çıkışta temizlik, 5 GB tavanı, gözetimsiz süre sınırı (#335)."""

from __future__ import annotations

import time

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import job_lifetime, shell
from fusion_cli.tools.jobs import job_status


@pytest.fixture(autouse=True)
def _etkilesimli():
    job_lifetime.clear_unattended()
    yield
    job_lifetime.clear_unattended()


def _kimlik(cikti: str) -> str:
    return cikti.split("Arka plan işi başladı: ", 1)[1].split()[0]


def test_etkilesimli_oturumda_sure_siniri_yok():
    assert job_lifetime.time_limit_s(5000, env={}) is None


@pytest.mark.parametrize(
    ("metin_istem", "istenen", "env", "beklenen"),
    [
        (False, None, {}, 1800.0),
        (True, None, {}, 600.0),
        (False, 60_000, {}, 60.0),
        (False, 99_999_999, {}, 7200.0),
        (False, None, {"BASH_DEFAULT_TIMEOUT_MS": "2400000"}, 2400.0),
        (False, None, {"BASH_DEFAULT_TIMEOUT_MS": "60000"}, 1800.0),  # kısaltmaz
        (True, None, {"BASH_DEFAULT_TIMEOUT_MS": "900000"}, 900.0),
        (False, 99_999_999, {"BASH_MAX_TIMEOUT_MS": "9000000"}, 9000.0),
    ],
)
def test_gozetimsiz_sure_siniri_claude_kurallari(metin_istem, istenen, env, beklenen):
    job_lifetime.set_unattended(text_prompt=metin_istem)
    assert job_lifetime.time_limit_s(istenen, env=env) == beklenen


def test_tasinan_komut_varsayilan_sinirdan_baslar():
    job_lifetime.set_unattended(text_prompt=False)
    assert job_lifetime.time_limit_s(5000, moved=True, env={}) == 1800.0


def test_oturum_kapanisinda_sahip_olunan_isler_durdurulur(tmp_path):
    context = ToolContext(root=tmp_path, shell_fingerprint=False)
    sonuc = shell.run_shell({"command": "sleep 30", "run_in_background": True}, context)
    kimlik = _kimlik(sonuc.output)
    assert job_lifetime.cleanup_owned_jobs() >= 1
    durum = job_status({"id": kimlik, "wait_s": 5}, context)
    assert "BİTTİ" in durum.output and "143" in durum.output


def test_sure_siniri_dolan_is_durdurulur_ve_nedeni_yazilir(tmp_path, monkeypatch):
    monkeypatch.setattr(job_lifetime, "_POLL_S", 0.1)
    job_lifetime.set_unattended(text_prompt=True)
    monkeypatch.setattr(job_lifetime, "time_limit_s", lambda *a, **k: 0.5)
    monkeypatch.setattr(shell, "time_limit_s", lambda *a, **k: 0.5)
    context = ToolContext(root=tmp_path, shell_fingerprint=False)
    sonuc = shell.run_shell({"command": "sleep 30", "run_in_background": True}, context)
    kimlik = _kimlik(sonuc.output)
    bitis = time.monotonic() + 8
    while not (tmp_path / ".fusion" / "is" / f"{kimlik}.exit").exists():
        assert time.monotonic() < bitis, "süre sınırında durdurulmadı"
        time.sleep(0.1)
    durum = job_status({"id": kimlik}, context)
    assert "süre sınırına" in durum.output


def test_5gb_tavani_asilinca_durdurur(tmp_path):
    gunluk = tmp_path / "is.log"
    gunluk.write_text("x", encoding="utf-8")
    assert job_lifetime._over_limit(gunluk, "k", None, 0) == ""
    with gunluk.open("r+b") as akis:
        akis.truncate(job_lifetime.MAX_OUTPUT_BYTES + 1)  # seyrek dosya, disk tutmaz
    assert "5 GB" in job_lifetime._over_limit(gunluk, "k", None, 0)


def test_on_plan_alt_ajaninin_isleri_grubuyla_durur_ana_konusmaninki_kalir(tmp_path):
    """Claude: ön plan alt ajanının başlattığı komut, alt ajanın koşusu bitince durur (#335)."""
    from fusion_cli.engines.agent.team_scope import derive_sub_context

    parent = ToolContext(root=tmp_path)
    child = derive_sub_context(parent, None)
    assert child.job_group and child.job_group != parent.job_group
    ana = _kimlik(
        shell.run_shell({"command": "sleep 30", "run_in_background": True}, parent).output
    )
    alt = _kimlik(shell.run_shell({"command": "sleep 30", "run_in_background": True}, child).output)

    assert job_lifetime.stop_group(child.job_group) == 1
    assert alt not in job_lifetime.running_owned()
    assert ana in job_lifetime.running_owned()
    assert "alt ajan bittiği için" in (tmp_path / ".fusion" / "is" / f"{alt}.log").read_text()
    assert job_lifetime.stop_group("") == 0
    job_lifetime.cleanup_owned_jobs()


def test_wait_owned_isler_bitince_doner_sure_dolunca_false(tmp_path):
    context = ToolContext(root=tmp_path)
    job_lifetime.cleanup_owned_jobs()
    shell.run_shell({"command": "sleep 0.3", "run_in_background": True}, context)
    assert job_lifetime.wait_owned(10, poll_s=0.05) is True
    shell.run_shell({"command": "sleep 30", "run_in_background": True}, context)
    assert job_lifetime.wait_owned(0.2, poll_s=0.05) is False
    job_lifetime.cleanup_owned_jobs()

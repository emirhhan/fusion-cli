"""`run_shell` için isteğe bağlı işletim sistemi sandbox'ı (Q1-16).

Ölçüldü (30 Ekim): `echo x > ../y` proje kökünün dışına yazabiliyordu; tek bariyer onay
metniydi. `runtime.shell_sandbox: write_root` macOS'ta `sandbox-exec` ile yazmayı kök +
geçici dizinlerle sınırlar. Varsayılan `off`: davranış değişmez.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from fusion_cli.config.loader import load_config
from fusion_cli.core import shell_sandbox
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.shell_sandbox_linux import LinuxTools
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import jobs, shell

_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")


def _sandbox_calisir() -> bool:
    """İç içe sandbox ya da kısıtlı ortamda sandbox-exec başlamayabilir."""
    if sys.platform != "darwin" or not _SANDBOX_EXEC.exists():
        return False
    probe = subprocess.run(
        [str(_SANDBOX_EXEC), "-p", "(version 1)(allow default)", "/usr/bin/true"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


macos_sandbox = pytest.mark.skipif(not _sandbox_calisir(), reason="sandbox-exec kullanılamıyor")


# --- plan (platformdan bağımsız) -------------------------------------------- #


def test_kapali_kipte_onek_bos_ve_uyari_yok(tmp_path):
    plan = shell_sandbox.plan_shell_sandbox("off", (tmp_path,), platform="darwin")
    assert plan.prefix == () and plan.notice == ""


def test_bilinmeyen_kip_kapali_sayilir(tmp_path):
    plan = shell_sandbox.plan_shell_sandbox("kapali-degil", (tmp_path,), platform="darwin")
    assert plan.prefix == ()


def test_linux_ta_bwrap_yoksa_uyarirla_kapali_kalir(tmp_path):
    """P-010: Linux artık bubblewrap ile desteklenir; bwrap yoksa eski uyarılı davranış."""
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (tmp_path,), platform="linux", linux_tools=LinuxTools(bwrap=None)
    )
    assert plan.prefix == ()
    assert "bwrap" in plan.notice and "kapalı" in plan.notice


def test_windows_ta_uyarirla_kapali_kalir(tmp_path):
    plan = shell_sandbox.plan_shell_sandbox("write_root", (tmp_path,), platform="win32")
    assert plan.prefix == ()
    assert "macOS ve Linux" in plan.notice and "kapalı" in plan.notice


def test_sandbox_exec_yoksa_uyarirla_kapali_kalir(tmp_path):
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (tmp_path,), platform="darwin", executable=None
    )
    assert plan.prefix == () and "sandbox-exec" in plan.notice


def test_profil_yollari_parametre_olarak_gecer_enjeksiyon_yok(tmp_path):
    kotu = tmp_path / 'a") (allow file-write* (subpath "/")'
    plan = shell_sandbox.plan_shell_sandbox(
        "write_root", (kotu,), platform="darwin", executable="/usr/bin/sandbox-exec"
    )
    profil = plan.prefix[plan.prefix.index("-p") + 1]
    assert str(kotu) not in profil
    assert f"W0={kotu.resolve()}" in plan.prefix
    assert '(subpath (param "W0"))' in profil
    assert "(deny file-write*)" in profil


# --- gerçek sandbox (yalnız macOS) ------------------------------------------ #


def _proje(tmp_path, monkeypatch):
    """Geçici dizin izni kaldırılır: tmp_path kardeşi kök dışı sayılsın."""
    monkeypatch.setattr(shell_sandbox, "_temporary_directories", lambda: ())
    root = tmp_path / "proje"
    root.mkdir()
    (tmp_path / "disari").mkdir()
    return root


@macos_sandbox
def test_kok_icine_yazar_kok_disina_yazamaz(tmp_path, monkeypatch):
    root = _proje(tmp_path, monkeypatch)
    context = ToolContext(root=root, shell_sandbox="write_root")

    ic = shell.run_shell({"command": "echo a > ic.txt"}, context)
    dis = shell.run_shell({"command": "echo b > ../disari/dis.txt"}, context)

    assert ic.ok and (root / "ic.txt").read_text() == "a\n"
    assert not dis.ok
    assert not (tmp_path / "disari" / "dis.txt").exists()
    assert "sandbox" in dis.output.lower()


@macos_sandbox
def test_varsayilan_off_kok_disina_yazmaya_devam_eder(tmp_path, monkeypatch):
    root = _proje(tmp_path, monkeypatch)
    context = ToolContext(root=root)

    sonuc = shell.run_shell({"command": "echo b > ../disari/dis.txt"}, context)

    assert sonuc.ok and (tmp_path / "disari" / "dis.txt").exists()


@macos_sandbox
def test_okuma_dev_null_ve_gecici_dizin_acik_kalir(tmp_path, monkeypatch):
    root = _proje(tmp_path, monkeypatch)
    monkeypatch.undo()  # gerçek geçici dizin izinleri
    context = ToolContext(root=root, shell_sandbox="write_root")
    gecici = tmp_path / "gecici-dosya"

    sonuc = shell.run_shell(
        {"command": f"cat /etc/hosts > /dev/null && echo hi 2>/dev/null > {gecici}"}, context
    )

    assert sonuc.ok and gecici.read_text() == "hi\n"


@macos_sandbox
def test_ek_kok_yazilabilir(tmp_path, monkeypatch):
    root = _proje(tmp_path, monkeypatch)
    context = ToolContext(root=root, extra_roots=(tmp_path / "disari",), shell_sandbox="write_root")

    assert shell.run_shell({"command": "echo b > ../disari/dis.txt"}, context).ok


@macos_sandbox
def test_arka_plan_isi_de_sandbox_icinde_calisir(tmp_path, monkeypatch):
    root = _proje(tmp_path, monkeypatch)
    context = ToolContext(root=root, shell_sandbox="write_root")

    basla = shell.run_shell(
        {"command": "echo b > ../disari/dis.txt; echo ic > ic.txt", "background": True}, context
    )
    kimlik = basla.output.split("Arka plan işi başladı: ", 1)[1].split()[0]
    jobs.job_status({"id": kimlik, "wait_s": 10}, context)

    assert (root / "ic.txt").exists()
    assert not (tmp_path / "disari" / "dis.txt").exists()


def test_desteklenmeyen_ortamda_uyari_bir_kez_gosterilir(tmp_path, monkeypatch):
    root = tmp_path
    monkeypatch.setattr(shell_sandbox.sys, "platform", "win32")
    shell._SHOWN_SANDBOX_NOTICES.clear()
    context = ToolContext(root=root, shell_sandbox="write_root")

    ilk = shell.run_shell({"command": "echo a"}, context)
    ikinci = shell.run_shell({"command": "echo a"}, context)

    assert ilk.ok and "FUSION_NOT" in ilk.output and "macOS ve Linux" in ilk.output
    assert "FUSION_NOT" not in ikinci.output


# --- yapılandırma ------------------------------------------------------------ #


def test_varsayilan_yapilandirma_off():
    assert load_config().runtime.shell_sandbox == "off"


def test_gecersiz_kip_yapilandirmada_reddedilir(tmp_path, monkeypatch):
    yol = tmp_path / "config.yaml"
    yol.write_text("runtime:\n  shell_sandbox: bilinmeyen\n")
    with pytest.raises(ConfigError, match="shell_sandbox"):
        load_config(yol)


def test_tirnaksiz_off_yaml_false_olsa_da_kabul_edilir(tmp_path):
    yol = tmp_path / "config.yaml"
    yol.write_text("runtime:\n  shell_sandbox: off\n")
    assert load_config(yol).runtime.shell_sandbox == "off"

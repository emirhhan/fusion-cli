"""Komut politikası P2 sapmaları (T1-19, T1-20)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.tools import auto_policy, command_policy
from fusion_cli.tools.command_paths import escapes_project

KOK = Path("/tmp/proje")


@pytest.mark.parametrize("komut", ["grep -r gizli .*", "ls .*", "cat .*", "ls ..*", "ls .?"])
def test_nokta_yildiz_joker_ust_dizine_cikar(komut):
    """T1-19: `.*` bash'te `..`'yi de kapsar; `normpath('.*')` ise "içeride" sanılıyordu."""
    assert not command_policy.is_unattended_safe(komut)


@pytest.mark.parametrize("komut", ["ls *.py", "cat src/*.txt", "ls .gitignore", "ls .env*"])
def test_zararsiz_joker_sorulmaz(komut):
    assert command_policy.is_unattended_safe(komut)


def test_escapes_nokta_yildiz():
    assert escapes_project("ls", [".*"])
    assert not escapes_project("ls", ["*.py"])


@pytest.mark.parametrize(
    "komut", ["npm --version", "go version", "cargo --version", "pnpm --version", "npm -v"]
)
def test_surum_sorgusu_sorulmaz(komut):
    """T1-20: `_VERSION_ONLY` içindeki go/cargo/npm dalı ölüydü; sürüm sorgusu soruluyordu."""
    if komut.endswith("-v"):
        pytest.skip("-v tanınan sürüm bayrağı değil")
    assert command_policy.is_unattended_safe(komut)


def test_npm_yalniz_argumansiz_hala_sorulur():
    assert not command_policy.is_unattended_safe("npm")


@pytest.mark.parametrize("komut", ["find . -fprintf out.txt x", "find . -fprint0 out.txt"])
def test_find_dosya_yazan_bayraklar_sorulur(komut):
    assert not command_policy.is_unattended_safe(komut)
    assert auto_policy.is_read_only_command(komut) is False


@pytest.mark.parametrize("komut", ["find . -okdir ls {} ;", "find . -fls out.txt"])
def test_find_okdir_fls_otomatik_kipte_salt_okur_degil(komut):
    assert auto_policy.is_read_only_command(komut) is False


@pytest.mark.parametrize("komut", ["top", "tail -f app.log", "tail -F app.log", "tail --follow x"])
def test_engelleyen_okuyucular_sorulur(komut):
    """`top` (etkileşimli) ve `tail -f` zaman aşımına kadar bloklar."""
    assert not command_policy.is_unattended_safe(komut)


@pytest.mark.parametrize("komut", ["top -l 1", "tail -n 5 app.log", "tail app.log"])
def test_bloklamayan_okuyucular_serbest(komut):
    assert command_policy.is_unattended_safe(komut)


@pytest.mark.parametrize(
    "komut", ["open indirilen.dmg", "open Uygulama.app", "open https://evil.example/x"]
)
def test_open_calistirilabilir_ve_uzak_hedefi_sorulur(komut):
    assert not command_policy.is_unattended_safe(komut)


@pytest.mark.parametrize("komut", ["open rapor.html", "open http://localhost:3000"])
def test_open_zararsiz_hedef_serbest(komut):
    assert command_policy.is_unattended_safe(komut)


def test_grep_e_os_remove_riskli_sayilmaz():
    assert auto_policy.auto_risk("grep -e os.remove src", KOK) is None


def test_python_c_satir_ici_kod_hala_denetlenir():
    assert auto_policy.auto_risk("python3 -c \"import os; os.remove('x')\"", KOK) is not None


def test_sayisal_son_arguman_dusurulmez():
    """`2>&1` kalıntısı yalnız yönlendirme bırakıntısıdır; `head -n 5` bölünmemeli."""
    assert command_policy._split("head -n 5 f 2>&1") == ["head -n 5 f"]
    assert command_policy._split("tail -n 5 2>&1") == ["tail -n 5"]
    # Çıplak sayı argümanı korunur: `python3 -c 1` -> yorumlayıcıya GİDEN argüman.
    assert command_policy._split("python3 -c 1") == ["python3 -c 1"]


# --- T2-21: git aracı ---------------------------------------------------------

from fusion_cli.core.tools import ToolContext  # noqa: E402
from fusion_cli.tools import shell  # noqa: E402
from fusion_cli.tools.command_semantics import git_reads_only  # noqa: E402


@pytest.mark.parametrize(
    "parcalar",
    [
        ["diff", "--ext-diff"],
        ["log", "--textconv", "-p"],
        ["grep", "-Ovim", "x"],  # grep zaten salt-okur listesinde değil
        ["diff", "--open-files-in-pager=vim"],
        ["show", "--output=/tmp/x"],
    ],
)
def test_git_dis_program_calistiran_bayraklar_salt_okur_degil(parcalar):
    assert not git_reads_only(parcalar)


@pytest.mark.parametrize("parcalar", [["diff", "--stat"], ["log", "-n", "3"], ["diff", "-Osira"]])
def test_git_zararsiz_bayraklar_salt_okur(parcalar):
    assert git_reads_only(parcalar)


def test_git_aracı_tirnakli_argumani_bozmaz(tmp_path):
    """`subcommand.split()` tırnakları anlamıyordu: --format="%h %s" ikiye bölünüyordu."""
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "f").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "f"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "ilk is"], cwd=tmp_path, check=True)

    sonuc = shell.git({"subcommand": 'log --format="%s|%an"'}, ToolContext(root=tmp_path))

    assert sonuc.ok, sonuc.output
    assert sonuc.output.strip() == "ilk is|t"


def test_git_ikili_cikti_istisna_atmaz(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "ikili.bin").write_bytes(b"\xff\xfe\x00\x80")
    subprocess.run(["git", "add", "ikili.bin"], cwd=tmp_path, check=True)

    sonuc = shell.git({"subcommand": "diff --cached --no-binary"}, ToolContext(root=tmp_path))

    assert isinstance(sonuc.output, str)

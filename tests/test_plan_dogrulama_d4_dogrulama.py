"""Dalga 4 (plan-dogrulama): adım doğrulama, kapı ve rapor bulguları (A4-14 ...)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.core.evidence import EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
from fusion_cli.engines.agent import step_verification as sv

# --- A4-14: git seçenekli çağrılarda alt komut doğru çıkarılır -------------------- #


@pytest.mark.parametrize(
    "komut",
    [
        "git --git-dir=.git commit -m x",
        "git -c a=b -C repo commit -m x",
        "git -C repo commit -m x",
        "git --no-pager commit -m x",
    ],
)
def test_git_secenekli_commit_tanınır(komut):
    """Ölçüldü (29 Ekim): `--git-dir=.git` değer-içi seçenekte `commit` atlanıyordu."""
    assert sv._contains_git_action(komut, "commit")


def test_git_baska_alt_komut_commit_sayilmaz():
    assert not sv._contains_git_action("git --git-dir=.git status", "commit")


# --- A4-53: 'var' alt dizesi ------------------------------------------------------ #


def test_eski_dosya_kosulu_varsayilan_kelimesine_takilmaz():
    from fusion_cli.core.execution_plan import PlanStep, RetrySafety

    adim = PlanStep(
        step_id="a",
        goal="g",
        depends_on=(),
        expected_effects=("file:a.txt",),
        allowed_tool_families=("files",),
        success_criteria=("dosya varsayılan ayarları içerir",),
        verification_hint="",
        retry_safety=RetrySafety.SAFE,
    )

    assert sv._legacy_file_check(adim, "dosya varsayılan ayarları içerir") is None
    assert sv._legacy_file_check(adim, "a.txt dosyası var") is not None


# --- A4-18: araç takma adı, boş expected, komut boşluğu --------------------------- #


def _cikti(*kullanimlar):
    return SimpleNamespace(tool_uses=tuple(kullanimlar))


def _kullanim(name, arguments=None, output=""):
    return SimpleNamespace(name=name, ok=True, arguments=arguments or {}, output=output)


def test_arac_kontrolu_takma_adi_ve_bos_expected_kabul_eder(tmp_path):
    kontrol = VerificationCheck("k", VerificationCheckKind.TOOL, "bash", "")
    kanit = sv._evaluate_check(
        kontrol,
        root=tmp_path,
        outcome=_cikti(_kullanim("run_shell", {"command": "ls"})),
        verification=None,
    )

    assert kanit.status is EvidenceStatus.PASSED


def test_komut_kontrolu_bosluk_farkini_tolere_eder(tmp_path):
    kontrol = VerificationCheck("k", VerificationCheckKind.COMMAND, "pytest   -q")
    kanit = sv._evaluate_check(
        kontrol,
        root=tmp_path,
        outcome=_cikti(_kullanim("run_shell", {"command": "python3 -m pytest -q"})),
        verification=None,
    )

    assert kanit.status is EvidenceStatus.PASSED


# --- A4-19: içerik kontrolü ------------------------------------------------------- #


def test_dosya_icerik_kontrolu_bosluk_farkini_tolere_eder_ve_kesifte_dusurmez(tmp_path):
    (tmp_path / "a.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    kontrol = VerificationCheck("k", VerificationCheckKind.FILE_CONTAINS, "a.py", "def  main()")
    assert sv.evaluate_file_check(kontrol, tmp_path).status is EvidenceStatus.PASSED

    yanlis = VerificationCheck("k", VerificationCheckKind.FILE_CONTAINS, "a.py", "def run():")
    assert sv.evaluate_file_check(yanlis, tmp_path).status is EvidenceStatus.FAILED
    assert (
        sv.evaluate_file_check(yanlis, tmp_path, step_mutates=False).status
        is EvidenceStatus.UNVERIFIED
    )


# --- A4-17: değişken gürültü önceden kırık kapıyı yeni kırılma yapmaz -------------- #


def test_zaman_damgasi_ve_sure_farki_yeni_bulgu_sayilmaz():
    onceki = (
        "pytest düştü (çıkış 1)\n[2026-10-29 10:00:00] 3 failed in 1.52s pid 123 /tmp/tmpab/x",
    )
    simdi = (
        "pytest düştü (çıkış 1)\n[2026-10-29 10:07:41] 3 failed in 2.08s pid 9981 /tmp/tmpzz/x",
    )

    assert sv.new_findings(simdi, onceki) == ()
    yeni = ("pytest düştü (çıkış 1)\n[2026-10-29 10:07:41] 4 failed in 2.08s pid 9981",)
    assert sv.new_findings(yeni, onceki) == yeni


# --- A4-15: manifest taraması bağımlılık klasörlerine girmez ----------------------- #


def test_manifest_taramasi_node_modules_a_girmez(tmp_path):
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "paket.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ASSETS.json").write_text("{}", encoding="utf-8")

    adlar = [p.name for p in sv._manifests(tmp_path)]

    assert adlar == ["ASSETS.json"]

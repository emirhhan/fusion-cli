"""Kabul alanı `kendini_gelistirme`: worktree yaşam döngüsü ve gizli testlerin mutant kanıtı."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from evals.kabul.areas import self_improve as area

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_gizli_olumlu_test_ozellik_yokken_duser():
    """Mutant kanıtı: bu deponun şimdiki kodunda `--url` yok, test KAÇMALI."""
    env = {"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin"}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(area.HIDDEN_TEST)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    assert completed.returncode != 0
    assert "test_url_ile_uzak_sunucu_eklenir" in completed.stdout
    assert "No such option: --url" in completed.stdout


def test_worktree_olusur_ve_cikista_temizlenir(tmp_path):
    with area.prepare(tmp_path) as values:
        repo = Path(values[area.REPO_KEY])
        assert (repo / "src" / "fusion_cli" / "cli" / "app.py").is_file()
        listed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert str(repo.resolve()) in listed

    assert not repo.exists()
    after = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert str(repo.resolve()) not in after


def test_degismemis_kopyada_ozellik_maddeleri_duser(tmp_path):
    with area.prepare(tmp_path) as values:
        inspection = area.inspect(tmp_path, values)

    result = {check.name: check.passed for check in inspection.checks}
    assert not inspection.invalid_reason
    assert result["gizli_testler_gecti"] is False
    assert result["test_eklendi"] is False
    assert result["yasak_yola_dokunulmadi"] is True
    assert result["ruff_temiz"] is True
    assert result["mypy_temiz"] is True
    assert result["config_writer_testleri_gecti"] is True


def test_test_eklenmis_ve_yasak_yola_dokunulmus_kopya_ayristirilir(tmp_path):
    with area.prepare(tmp_path) as values:
        repo = Path(values[area.REPO_KEY])
        (repo / "tests" / "test_yeni.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
        (repo / "evals" / "ek.py").write_text("X = 1\n", encoding="utf-8")
        checks = {check.name: check for check in area._git_checks(repo)}

    assert checks["test_eklendi"].passed is True
    assert checks["yasak_yola_dokunulmadi"].passed is False
    assert "evals/ek.py" in checks["yasak_yola_dokunulmadi"].detail


def test_kopya_yolu_yoksa_denetim_gecersiz(tmp_path):
    assert area.inspect(tmp_path, {}).invalid_reason
    assert area.inspect(tmp_path, {area.REPO_KEY: str(tmp_path / "yok")}).invalid_reason


def test_alan_tanimi_kopyayi_calisma_koku_yapar():
    assert area.AREA.name == "kendini_gelistirme"
    assert area.AREA.root_key == area.REPO_KEY
    assert area.AREA.timeout_s == 3600.0

"""Test kurcalama denetimi (yol haritası 5a): işaretle, engelleme, yanlış alarm verme."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.changeset import ChangeSet
from fusion_cli.core.evidence import ToolUse
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.tamper_check import (
    TamperKind,
    detect_test_tampering,
    is_ci_file,
    is_test_file,
    task_requests_test_work,
)
from fusion_cli.engines.agent.turn_report import build_turn_report, evidence_payload

from .test_plan_runner import _FakeDeps

ESKI_TEST = """\
import pytest


def test_toplam():
    assert topla(1, 2) == 3
    assert topla(0, 0) == 0


def test_negatif():
    assert topla(-1, -1) == -2
"""


def _kur(tmp_path: Path, ad: str, icerik: str) -> Path:
    yol = tmp_path / ad
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(icerik, encoding="utf-8")
    return yol


def _degistir(changes: ChangeSet, yol: Path, yeni: str | None) -> None:
    """Ajanın yazma aracı gibi: önce ilk hâli kaydet, sonra yaz (None = sil)."""
    changes.record(yol)
    if yeni is None:
        yol.unlink()
    else:
        yol.write_text(yeni, encoding="utf-8")


def _bul(tmp_path: Path, changes: ChangeSet, task: str = "", uses: tuple[ToolUse, ...] = ()):
    return detect_test_tampering(changes, tmp_path, uses, task=task)


def _turler(bulgular) -> set[TamperKind]:
    return {b.kind for b in bulgular}


# --- yol sınıflandırması ---------------------------------------------------


@pytest.mark.parametrize(
    "yol",
    [
        "tests/test_a.py",
        "src/x/test_b.py",
        "pkg/b_test.go",
        "web/a.spec.ts",
        "web/a.test.js",
        "conftest.py",
        "tests/helpers.py",
        "app/__tests__/x.tsx",
    ],
)
def test_test_dosyalari_taninir(yol: str) -> None:
    assert is_test_file(yol)


@pytest.mark.parametrize("yol", ["src/a.py", "tests/fixtures/veri.json", "README.md", "latest.py"])
def test_test_olmayan_dosyalar_taninmaz(yol: str) -> None:
    assert not is_test_file(yol)


@pytest.mark.parametrize(
    "yol",
    [".github/workflows/ci.yml", "pytest.ini", "Makefile", "package.json", "pyproject.toml"],
)
def test_ci_dosyalari_taninir(yol: str) -> None:
    assert is_ci_file(yol)


# --- test dosyası içerik karşılaştırması -----------------------------------


def test_skip_eklemek_zayiflatma_sayilir(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(
        changes,
        yol,
        ESKI_TEST.replace("def test_negatif", "@pytest.mark.skip\ndef test_negatif"),
    )

    bulgular = _bul(tmp_path, changes)

    assert TamperKind.SKIP_ADDED in _turler(bulgular)
    assert all(b.weakens for b in bulgular if b.kind is TamperKind.SKIP_ADDED)


def test_assert_silmek_zayiflatma_sayilir(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(changes, yol, ESKI_TEST.replace("    assert topla(0, 0) == 0\n", ""))

    assert TamperKind.ASSERT_REMOVED in _turler(_bul(tmp_path, changes))


def test_assert_yorumlamak_silmekle_aynidir(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(changes, yol, ESKI_TEST.replace("    assert topla(0, 0)", "    # assert topla(0, 0)"))

    assert TamperKind.ASSERT_REMOVED in _turler(_bul(tmp_path, changes))


def test_test_islevi_silmek_isaretlenir(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(changes, yol, ESKI_TEST.split("def test_negatif")[0])

    assert TamperKind.TEST_REMOVED in _turler(_bul(tmp_path, changes))


def test_test_dosyasini_silmek_isaretlenir(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(changes, yol, None)

    assert _turler(_bul(tmp_path, changes)) == {TamperKind.TEST_DELETED}


def test_beklenen_degeri_degistirmek_yalniz_dokunus_uyarisidir(tmp_path: Path) -> None:
    """assert sayısı aynı: zayıflatma izi yok ama test turda değişti (uyarı)."""
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(changes, yol, ESKI_TEST.replace("== 3", "== 4"))

    bulgular = _bul(tmp_path, changes)

    assert _turler(bulgular) == {TamperKind.TEST_TOUCHED}
    assert not bulgular[0].weakens


def test_yeni_test_dosyasi_eklemek_alarm_vermez(tmp_path: Path) -> None:
    yol = tmp_path / "tests" / "test_yeni.py"
    yol.parent.mkdir(parents=True)
    changes = ChangeSet()
    changes.record_created(yol)
    yol.write_text("def test_x():\n    assert True\n", encoding="utf-8")

    assert _bul(tmp_path, changes) == ()


def test_degismeyen_icerik_alarm_vermez(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(changes, yol, ESKI_TEST)

    assert _bul(tmp_path, changes) == ()


def test_test_olmayan_dosya_degisikligi_alarm_vermez(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "src/a.py", "x = 1\n")
    changes = ChangeSet()
    _degistir(changes, yol, "x = 2\n")

    assert _bul(tmp_path, changes) == ()


# --- test işi görevinde yanlış alarm ---------------------------------------


@pytest.mark.parametrize(
    "gorev",
    [
        "tests/test_a.py için yeni testler yaz",
        "başarısız testi düzelt",
        "birim testi ekle",
        "write tests for the parser",
        "fix the failing test",
    ],
)
def test_test_isi_gorevleri_taninir(gorev: str) -> None:
    assert task_requests_test_work(gorev)


@pytest.mark.parametrize(
    "gorev",
    [
        "hatayı düzelt, testler geçsin",
        "testleri çalıştır, hata varsa düzelt",
        "make tests pass",
        "",
    ],
)
def test_testi_gecirme_istegi_test_isi_degildir(gorev: str) -> None:
    assert not task_requests_test_work(gorev)


def test_test_isinde_assert_azalmasi_alarm_vermez_ama_skip_verir(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(changes, yol, ESKI_TEST.replace("    assert topla(0, 0) == 0\n", ""))
    assert _bul(tmp_path, changes, task="testi düzelt") == ()

    _degistir(
        changes, yol, ESKI_TEST.replace("def test_negatif", "@pytest.mark.skip\ndef test_negatif")
    )
    assert TamperKind.SKIP_ADDED in _turler(_bul(tmp_path, changes, task="testi düzelt"))


def test_test_isinde_dokunus_uyarisi_yok(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(changes, yol, ESKI_TEST.replace("== 3", "== 4"))

    assert _bul(tmp_path, changes, task="topla için testleri güncelle") == ()


# --- CI / yapılandırma -----------------------------------------------------


def test_package_json_test_betigi_degisirse_isaretlenir(tmp_path: Path) -> None:
    eski = '{"scripts": {"test": "vitest run", "build": "tsc"}, "dependencies": {}}'
    yol = _kur(tmp_path, "package.json", eski)
    changes = ChangeSet()
    _degistir(changes, yol, eski.replace("vitest run", "echo ok"))

    assert _turler(_bul(tmp_path, changes)) == {TamperKind.CI_CHANGED}


def test_package_json_bagimlilik_eklemek_alarm_vermez(tmp_path: Path) -> None:
    eski = '{"scripts": {"test": "vitest run"}, "dependencies": {}}'
    yol = _kur(tmp_path, "package.json", eski)
    changes = ChangeSet()
    _degistir(changes, yol, eski.replace('"dependencies": {}', '"dependencies": {"a": "1"}'))

    assert _bul(tmp_path, changes) == ()


def test_pyproject_pytest_bolumu_degisirse_isaretlenir(tmp_path: Path) -> None:
    eski = '[project]\nname = "x"\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'
    yol = _kur(tmp_path, "pyproject.toml", eski)
    changes = ChangeSet()
    _degistir(changes, yol, eski.replace('addopts = "-q"', 'addopts = "-q --ignore=tests"'))
    assert TamperKind.CI_CHANGED in _turler(_bul(tmp_path, changes))


def test_pyproject_pytest_disi_degisiklik_alarm_vermez(tmp_path: Path) -> None:
    eski = '[project]\nname = "x"\n\n[tool.pytest.ini_options]\naddopts = "-q"\n'
    yol = _kur(tmp_path, "pyproject.toml", eski)
    changes = ChangeSet()
    _degistir(changes, yol, eski.replace('name = "x"', 'name = "y"'))

    assert _bul(tmp_path, changes) == ()


def test_makefile_test_hedefi_degisirse_isaretlenir(tmp_path: Path) -> None:
    eski = "build:\n\tgo build ./...\n\ntest:\n\tgo test ./...\n"
    yol = _kur(tmp_path, "Makefile", eski)
    changes = ChangeSet()
    _degistir(changes, yol, eski.replace("go test ./...", "true"))
    assert TamperKind.CI_CHANGED in _turler(_bul(tmp_path, changes))


def test_makefile_build_hedefi_degisikligi_alarm_vermez(tmp_path: Path) -> None:
    eski = "build:\n\tgo build ./...\n\ntest:\n\tgo test ./...\n"
    yol = _kur(tmp_path, "Makefile", eski)
    changes = ChangeSet()
    _degistir(changes, yol, eski.replace("go build ./...", "go build -v ./..."))

    assert _bul(tmp_path, changes) == ()


def test_ci_is_akisi_degisirse_isaretlenir(tmp_path: Path) -> None:
    eski = "jobs:\n  t:\n    steps:\n      - run: pytest\n"
    yol = _kur(tmp_path, ".github/workflows/ci.yml", eski)
    changes = ChangeSet()
    _degistir(changes, yol, eski.replace("pytest", "pytest || true"))

    assert _turler(_bul(tmp_path, changes)) == {TamperKind.CI_CHANGED}


# --- kabuk komutları -------------------------------------------------------


def _shell(komut: str) -> ToolUse:
    return ToolUse(
        "run_shell", mutating=True, arguments={"command": komut}, output="(çıkış kodu 0)"
    )


@pytest.mark.parametrize(
    "komut",
    [
        "rm tests/test_a.py",
        "git rm -q tests/test_a.py",
        "mv tests/test_a.py /tmp/x.py",
        "sed -i 's/assert/pass #/' tests/test_a.py",
        "echo '' > tests/test_a.py",
        "cd app && rm -f web/a.spec.ts",
    ],
)
def test_kabuk_ile_test_dosyasi_degistirme_isaretlenir(tmp_path: Path, komut: str) -> None:
    bulgular = _bul(tmp_path, ChangeSet(), uses=(_shell(komut),))

    assert _turler(bulgular) == {TamperKind.SHELL_MUTATION}


@pytest.mark.parametrize(
    "komut",
    ["pytest tests/test_a.py -q", "cat tests/test_a.py", "rm -rf build", "ls tests"],
)
def test_zararsiz_kabuk_komutu_alarm_vermez(tmp_path: Path, komut: str) -> None:
    assert _bul(tmp_path, ChangeSet(), uses=(_shell(komut),)) == ()


# --- tur raporu: kanıt kapısına bağlama ------------------------------------

GECEN_PYTEST = ToolUse(
    "run_shell", mutating=True, arguments={"command": "pytest -q"}, output="(çıkış kodu 0)\nok"
)


def _bulgular_skip(tmp_path: Path):
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(
        changes, yol, ESKI_TEST.replace("def test_negatif", "@pytest.mark.skip\ndef test_negatif")
    )
    return _bul(tmp_path, changes)


def test_zayiflatma_varken_gecen_test_dogrulama_sayilmaz(tmp_path: Path) -> None:
    uses = (
        ToolUse("edit_file", mutating=True, arguments={"path": "tests/test_a.py"}),
        GECEN_PYTEST,
    )
    temiz = build_turn_report(("tests/test_a.py",), uses, gate=None)
    supheli = build_turn_report(
        ("tests/test_a.py",), uses, gate=None, test_tamper=_bulgular_skip(tmp_path)
    )

    assert temiz.is_verified is True
    assert supheli.is_verified is False
    metin = supheli.render()
    assert "ŞÜPHELİ TEST DEĞİŞİKLİĞİ" in metin
    assert "✓ Doğrulandı" not in metin
    assert "sayılmaz" in metin.casefold()


def test_yalniz_dokunus_dogrulamayi_dusurmez_ama_uyarir(tmp_path: Path) -> None:
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    changes = ChangeSet()
    _degistir(changes, yol, ESKI_TEST.replace("== 3", "== 4"))
    uses = (
        ToolUse("edit_file", mutating=True, arguments={"path": "tests/test_a.py"}),
        GECEN_PYTEST,
    )

    rapor = build_turn_report(
        ("tests/test_a.py",), uses, gate=None, test_tamper=_bul(tmp_path, changes)
    )

    assert rapor.is_verified is True
    assert "Mevcut test dosyası da değiştirildi" in rapor.render()


def test_kabukla_silme_degisiklik_kaydi_olmasa_da_raporlanir(tmp_path: Path) -> None:
    bulgular = _bul(tmp_path, ChangeSet(), uses=(_shell("rm tests/test_a.py"),))
    rapor = build_turn_report((), (_shell("rm tests/test_a.py"),), gate=None, test_tamper=bulgular)

    assert rapor.is_verified is False
    assert "tests/test_a.py" in rapor.render()


def test_kanit_ozeti_supheli_alani_yalniz_bulgu_varken_tasir(tmp_path: Path) -> None:
    bos = evidence_payload(build_turn_report(("a.py",), (), gate=None))
    assert bos is not None and "supheli_test_degisikligi" not in bos

    dolu = evidence_payload(
        build_turn_report(("a.py",), (), gate=None, test_tamper=_bulgular_skip(tmp_path))
    )
    assert dolu is not None
    assert dolu["supheli_test_degisikligi"]["zayiflatan"] >= 1


# --- tur sonu: loop._apply_turn_report -------------------------------------


def _tur(tmp_path: Path, *, metin: str, task: str = "", ayar: bool | None = None):
    context = ToolContext(tmp_path)
    yol = _kur(tmp_path, "tests/test_a.py", ESKI_TEST)
    _degistir(
        context.changes,
        yol,
        ESKI_TEST.replace("def test_negatif", "@pytest.mark.skip\ndef test_negatif"),
    )
    uses = (
        ToolUse("edit_file", mutating=True, arguments={"path": "tests/test_a.py"}),
        GECEN_PYTEST,
    )
    deps = _FakeDeps(context)
    if ayar is not None:
        from types import SimpleNamespace

        deps.config = SimpleNamespace(runtime=SimpleNamespace(test_tamper_check=ayar))
    outcome = loop.AgentOutcome(final_text=metin, messages=[], tool_uses=uses)
    loop._apply_turn_report(outcome, deps, gate=VerificationResult(ok=True), task=task)
    return outcome, deps


def test_testler_gecti_iddiasi_supheli_degisiklikle_basari_sayilmaz(tmp_path: Path) -> None:
    outcome, deps = _tur(tmp_path, metin="Bitti, tüm testler geçti.")

    assert outcome.ok is False
    assert outcome.completion_report.false_claim is True
    assert "ŞÜPHELİ TEST DEĞİŞİKLİĞİ" in outcome.final_text
    olay = [e for e in deps.publisher.events if type(e).__name__ == "TamperSuspected"]
    assert olay and olay[0].weakening >= 1 and "atlama_eklendi" in olay[0].kinds


def test_iddia_yoksa_tur_engellenmez_yalniz_isaretlenir(tmp_path: Path) -> None:
    outcome, _ = _tur(tmp_path, metin="Değişiklikleri yaptım.")

    assert outcome.ok is True
    assert "ŞÜPHELİ TEST DEĞİŞİKLİĞİ" in outcome.final_text


def test_ayar_kapaliyken_denetim_calismaz(tmp_path: Path) -> None:
    outcome, deps = _tur(tmp_path, metin="testler geçti", ayar=False)

    assert outcome.completion_report.test_tamper == ()
    assert "ŞÜPHELİ" not in outcome.final_text
    assert not [e for e in deps.publisher.events if type(e).__name__ == "TamperSuspected"]

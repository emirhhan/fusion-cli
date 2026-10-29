"""Test geçtikten sonra kod yeniden değişirse eski başarı kanıt sayılmaz (WP06).

Ölçüldü (29 Ekim): "son dosya değişikliği" yalnız dosya araçlarından okunuyordu.
`edit_file` → `pytest` (geçti) → `run_shell "sed -i ..."` sırasında rapor
`is_verified=True` dedi; oysa test, değişmiş kodu hiç görmemişti. Kabukla dosya
değiştirebilecek komut da artık son mutasyon sayılır; salt-okur komutlar, doğrulama
komutlarının kendisi ve yalnız Git geçmişine yazan komutlar sayılmaz.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.evidence import ToolUse
from fusion_cli.engines.agent.turn_report import build_turn_report

_EDIT = ToolUse("edit_file", mutating=True, arguments={"path": "app.py"}, output="ok")


def _shell(command: str, code: int = 0) -> ToolUse:
    return ToolUse(
        "run_shell", mutating=True, arguments={"command": command}, output=f"(çıkış kodu {code})\n"
    )


@pytest.mark.parametrize(
    "degistiren",
    [
        "sed -i '' 's/return 1/return 2/' app.py",
        "python3 scripts/yeniden_yaz.py > app.py",
        "cp yedek/app.py app.py",
        "npm install lodash",
    ],
)
def test_testten_sonra_kabukla_degisiklik_eski_basariyi_gecersiz_kilar(degistiren):
    uses = (_EDIT, _shell("pytest -q"), _shell(degistiren))

    report = build_turn_report(("app.py",), uses, None, require_behavioral_evidence=True)

    assert report.is_verified is False
    assert report.blocks_success


@pytest.mark.parametrize(
    "zararsiz",
    ["git add -A", "git commit -m 'fix: x'", "git status", "cat app.py", "ls -la", "git log -1"],
)
def test_okuyan_ve_yalniz_gecmise_yazan_komut_kaniti_bozmaz(zararsiz):
    uses = (_EDIT, _shell("pytest -q"), _shell(zararsiz))

    report = build_turn_report(("app.py",), uses, None, require_behavioral_evidence=True)

    assert report.is_verified is True


def test_kabukla_degisiklikten_sonra_yeniden_test_kanit_olur():
    uses = (_EDIT, _shell("pytest -q"), _shell("sed -i '' 's/a/b/' app.py"), _shell("pytest -q"))

    assert build_turn_report(("app.py",), uses, None).is_verified is True


def test_zaman_asimi_ve_okunamayan_cikis_basari_sayilmaz():
    zaman_asimi = ToolUse(
        "run_shell", mutating=True, arguments={"command": "pytest -q"}, output="zaman aşımı"
    )

    report = build_turn_report(("app.py",), (_EDIT, zaman_asimi), None)

    assert report.is_verified is not True


@pytest.mark.parametrize(
    "test_komutu", ["pytest -q 2>&1", "pytest -q 2>&1 | tail -20", "npm test 2>/dev/null"]
)
def test_ciktisi_yonlendirilen_test_komutu_mutasyon_sayilmaz(test_komutu):
    uses = (_EDIT, _shell("pytest -q"), _shell(test_komutu))

    assert build_turn_report(("app.py",), uses, None).is_verified is True


# İnceleme turu (29 Ekim): zincirler parça parça; statik denetim ve derleme kanıtı bozmaz.
@pytest.mark.parametrize(
    "degistiren",
    [
        "pytest && sed -i '' s/a/b/ app.py",
        "git add . && rm app.py",
        "git commit -m x; rm -rf src",
        "git push && git checkout .",
        "pytest -q\nsed -i '' s/a/b/ app.py",
        "ruff check --fix .",
        "npx eslint --fix .",
        "cat a.txt | tee app.py",
    ],
)
def test_zincirin_herhangi_bir_parcasi_degistiriyorsa_mutasyondur(degistiren):
    uses = (_EDIT, _shell("pytest -q"), _shell(degistiren))

    assert build_turn_report(("app.py",), uses, None).is_verified is False


@pytest.mark.parametrize(
    "zararsiz",
    [
        "npm run build",
        "make",
        "cargo check",
        "tsc --noEmit",
        "npx eslint .",
        "ruff check .",
        "python -m mypy src",
        "python3 -m py_compile app.py",
        "uv run pytest -q",
        "git -C repo status",
        "git stash list",
        "pytest -q; echo $?",
        "pytest &>/dev/null",
        'pytest -k "a>b"',
        "pytest 2>&1 | tee test.log",
        "curl -s http://localhost:3000",
    ],
)
def test_statik_denetim_derleme_ve_okuma_kaniti_bozmaz(zararsiz):
    uses = (_EDIT, _shell("pytest -q"), _shell(zararsiz))

    assert build_turn_report(("app.py",), uses, None).is_verified is True

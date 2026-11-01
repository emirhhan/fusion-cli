"""Hata düzeltmede kanıt İKİ parçalıdır: önce kırmızı, sonra yeşil.

Agentless ve ReProAgent'ın ölçtüğü şey: düzeltmenin doğruluğu, hatayı gösteren bir
testin önce başarısız sonra başarılı olmasıyla kanıtlanır. Yalnız "şimdi geçiyor"
demek, testin hatayı hiç yakalamadığı durumu (fail-to-fail) gizler — bu, yanlış
başarının en yaygın kaynağıdır.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.evidence import EvidenceEnvironment, EvidenceStatus, ToolUse
from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
from fusion_cli.engines.agent.reproduction import evaluate_reproduction


def _calisma(command: str, ok: bool) -> ToolUse:
    return ToolUse(
        name="run_shell",
        ok=ok,
        mutating=False,
        arguments={"command": command},
        output="1 failed" if not ok else "1 passed",
    )


CHECK = VerificationCheck(
    criterion_id="hata düzeltildi",
    kind=VerificationCheckKind.REPRODUCTION,
    target="python -m pytest -q test_ortalama.py",
)


def test_once_kirmizi_sonra_yesil_kanit_sayilir():
    kanit = evaluate_reproduction(
        CHECK,
        tool_uses=(_identified(ok=False), _identified(ok=True)),
    )

    assert kanit.status is EvidenceStatus.PASSED
    assert "kırmızı" in kanit.summary.casefold()


def test_yalniz_yesil_dogrulanmis_sayilmaz():
    """Test hatayı hiç yakalamamış olabilir; 'şimdi geçiyor' kanıt değildir."""
    kanit = evaluate_reproduction(CHECK, tool_uses=(_identified(ok=True),))

    assert kanit.status is EvidenceStatus.UNVERIFIED
    assert "kırmızı" in kanit.summary.casefold()


def test_hala_kirmizi_ise_basarisiz():
    kanit = evaluate_reproduction(
        CHECK,
        tool_uses=(_identified(ok=False), _identified(ok=False)),
    )

    assert kanit.status is EvidenceStatus.FAILED


def test_hic_calistirilmadiysa_dogrulanamadi():
    kanit = evaluate_reproduction(CHECK, tool_uses=())

    assert kanit.status is EvidenceStatus.UNVERIFIED
    assert kanit.command == CHECK.target


def test_yesilden_kirmiziya_giden_sira_kanit_degildir():
    """Sıra önemlidir: önce geçip sonra düşen test, düzeltmeyi değil bozmayı gösterir."""
    kanit = evaluate_reproduction(
        CHECK,
        tool_uses=(_identified(ok=True), _identified(ok=False)),
    )

    assert kanit.status is EvidenceStatus.FAILED


def _identified(ok: bool, *, source: str = "") -> ToolUse:
    return replace(
        _calisma(CHECK.target, ok),
        source_digest=source or ("new" if ok else "old"),
        source_after_digest=source or ("new" if ok else "old"),
        environment=EvidenceEnvironment(CHECK.target, "/repo", "python", "deps", "config"),
        call_id="green" if ok else "red",
    )


def test_measured_same_environment_changed_source_proves_fix():
    result = evaluate_reproduction(CHECK, tool_uses=(_identified(False), _identified(True)))
    assert result.status is EvidenceStatus.PASSED
    assert result.source_digest == "new"
    assert result.call_id == "green"


def test_legacy_red_green_without_identity_stays_unverified():
    result = evaluate_reproduction(
        CHECK, tool_uses=(_calisma(CHECK.target, False), _calisma(CHECK.target, True))
    )
    assert result.status is EvidenceStatus.UNVERIFIED


@pytest.mark.parametrize(
    "field,value",
    [
        ("cwd", "/other"),
        ("config_digest", "other"),
        ("runtime", "other"),
        ("dependency_digest", "other"),
    ],
)
def test_different_measured_environment_cannot_prove_fix(field, value):
    red, green = _identified(False), _identified(True)
    green = replace(green, environment=replace(green.environment, **{field: value}))
    assert evaluate_reproduction(CHECK, tool_uses=(red, green)).status is EvidenceStatus.UNVERIFIED


@pytest.mark.parametrize(
    "command",
    [
        "cd other && python -m pytest -q test_ortalama.py",
        "python -m pytest -k other -q test_ortalama.py",
        "python -m pytest -c other.ini -q test_ortalama.py",
    ],
)
def test_meaningful_command_changes_are_not_same_reproduction(command):
    red = replace(_identified(False), arguments={"command": command})
    assert (
        evaluate_reproduction(CHECK, tool_uses=(red, _identified(True))).status
        is EvidenceStatus.UNVERIFIED
    )


def test_unchanged_source_cannot_explain_red_green():
    assert (
        evaluate_reproduction(
            CHECK, tool_uses=(_identified(False, source="same"), _identified(True, source="same"))
        ).status
        is EvidenceStatus.UNVERIFIED
    )


def test_missing_runner_is_not_bug_reproduction():
    red = replace(_identified(False), output="/python: No module named pytest")
    assert (
        evaluate_reproduction(CHECK, tool_uses=(red, _identified(True))).status
        is EvidenceStatus.UNVERIFIED
    )


def test_mutating_reproduction_command_is_not_stable_evidence():
    green = replace(_identified(True), source_after_digest="later")
    assert (
        evaluate_reproduction(CHECK, tool_uses=(_identified(False), green)).status
        is EvidenceStatus.UNVERIFIED
    )


def test_initially_green_then_red_green_is_not_original_bug_proof():
    uses = (_identified(True, source="initial"), _identified(False), _identified(True))
    assert evaluate_reproduction(CHECK, tool_uses=uses).status is EvidenceStatus.UNVERIFIED


def test_cosmetic_command_spacing_does_not_change_measured_identity():
    command = "python  -m pytest -q 'test_ortalama.py'"
    red = _identified(False)
    red = replace(
        red, arguments={"command": command}, environment=replace(red.environment, command=command)
    )
    assert (
        evaluate_reproduction(CHECK, tool_uses=(red, _identified(True))).status
        is EvidenceStatus.PASSED
    )


def test_environment_command_must_match_actual_call():
    red = _identified(False)
    green = _identified(True)
    red = replace(red, environment=replace(red.environment, command="pytest -q other.py"))
    green = replace(green, environment=red.environment)
    assert evaluate_reproduction(CHECK, tool_uses=(red, green)).status is EvidenceStatus.UNVERIFIED


@pytest.mark.parametrize(
    "first,second",
    [
        ("pytest -q 'test_*.py'", "pytest -q test_*.py"),
        ('pytest -q "test_?.py"', "pytest -q test_?.py"),
        ("pytest -q 'test_[ab].py'", "pytest -q test_[ab].py"),
        ("pytest '$HOME/test.py'", "pytest $HOME/test.py"),
        ("'OPTION=value' pytest", "OPTION=value pytest"),
    ],
)
def test_shell_significant_quoting_is_not_cosmetic(first, second):
    from fusion_cli.engines.agent.reproduction import _normalize

    assert _normalize(first) != _normalize(second)


def test_escaped_trailing_newline_is_not_stripped_from_shell_identity():
    from fusion_cli.engines.agent.reproduction import _normalize

    escaped = "pytest test_file.py " + "\\"
    assert _normalize(escaped + "\n") != _normalize(escaped)

"""Hata düzeltmede kanıt İKİ parçalıdır: önce kırmızı, sonra yeşil.

Agentless ve ReProAgent'ın ölçtüğü şey: düzeltmenin doğruluğu, hatayı gösteren bir
testin önce başarısız sonra başarılı olmasıyla kanıtlanır. Yalnız "şimdi geçiyor"
demek, testin hatayı hiç yakalamadığı durumu (fail-to-fail) gizler — bu, yanlış
başarının en yaygın kaynağıdır.
"""

from __future__ import annotations

from fusion_cli.core.evidence import EvidenceStatus, ToolUse
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
        tool_uses=(_calisma(CHECK.target, ok=False), _calisma(CHECK.target, ok=True)),
    )

    assert kanit.status is EvidenceStatus.PASSED
    assert "kırmızı" in kanit.summary.casefold()


def test_yalniz_yesil_dogrulanmis_sayilmaz():
    """Test hatayı hiç yakalamamış olabilir; 'şimdi geçiyor' kanıt değildir."""
    kanit = evaluate_reproduction(CHECK, tool_uses=(_calisma(CHECK.target, ok=True),))

    assert kanit.status is EvidenceStatus.UNVERIFIED
    assert "kırmızı" in kanit.summary.casefold()


def test_hala_kirmizi_ise_basarisiz():
    kanit = evaluate_reproduction(
        CHECK,
        tool_uses=(_calisma(CHECK.target, ok=False), _calisma(CHECK.target, ok=False)),
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
        tool_uses=(_calisma(CHECK.target, ok=True), _calisma(CHECK.target, ok=False)),
    )

    assert kanit.status is EvidenceStatus.FAILED

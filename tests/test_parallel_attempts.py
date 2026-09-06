"""Aynı adımı N kez dene, kazananı KANITLA seç.

Yürütme tabanlı doğrulayıcılarla Best@K'de belirgin kazanç ölçülmüş durumda;
Agentless'ın seçim aşaması da reprodüksiyon + regresyon + oy kullanıyor. Fusion'ın
avantajı ücretsiz sağlayıcılarla çalışması: paralel deneme burada doğal.

Seçim MODEL BEYANINA değil kanıta bakar. Hiçbir aday kanıt üretemezse hiçbiri
kazanmaz: yanlış adayı uygulamak, hiç denememekten kötüdür.
"""

from __future__ import annotations

from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheckKind
from fusion_cli.engines.agent.attempts import Attempt, choose_attempt


def _kanit(status: EvidenceStatus, criterion: str = "k1") -> CriterionEvidence:
    return CriterionEvidence(
        criterion_id=criterion,
        kind=VerificationCheckKind.COMMAND,
        status=status,
        summary="",
    )


def _aday(ad: str, *kanitlar: CriterionEvidence, ok: bool = True, calls: int = 3) -> Attempt:
    return Attempt(name=ad, ok=ok, criteria=kanitlar, model_calls=calls)


def test_en_cok_dogrulanmis_kosulu_olan_kazanir():
    kazanan = choose_attempt(
        [
            _aday("a", _kanit(EvidenceStatus.PASSED)),
            _aday("b", _kanit(EvidenceStatus.PASSED), _kanit(EvidenceStatus.PASSED, "k2")),
        ]
    )

    assert kazanan is not None and kazanan.name == "b"


def test_basarisiz_kanit_adayi_eler():
    kazanan = choose_attempt(
        [
            _aday("a", _kanit(EvidenceStatus.FAILED), _kanit(EvidenceStatus.PASSED, "k2")),
            _aday("b", _kanit(EvidenceStatus.PASSED)),
        ]
    )

    assert kazanan is not None and kazanan.name == "b"


def test_hicbir_aday_kanit_uretmediyse_kazanan_yok():
    """Yanlış adayı uygulamak, hiç denememekten kötüdür."""
    kazanan = choose_attempt([_aday("a", _kanit(EvidenceStatus.UNVERIFIED)), _aday("b", ok=False)])

    assert kazanan is None


def test_esitlikte_daha_az_cagri_harcayan_kazanir():
    kazanan = choose_attempt(
        [
            _aday("pahali", _kanit(EvidenceStatus.PASSED), calls=9),
            _aday("ucuz", _kanit(EvidenceStatus.PASSED), calls=2),
        ]
    )

    assert kazanan is not None and kazanan.name == "ucuz"


def test_tek_aday_kanitliysa_secilir():
    kazanan = choose_attempt([_aday("tek", _kanit(EvidenceStatus.PASSED))])

    assert kazanan is not None and kazanan.name == "tek"


def test_bos_liste_kazanan_uretmez():
    assert choose_attempt([]) is None

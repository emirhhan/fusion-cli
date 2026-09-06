"""Reprodüksiyon kanıtı: önce kırmızı, sonra yeşil.

Agentless ve ReProAgent'ın ölçtüğü şey şu: bir düzeltmenin doğruluğu, hatayı
gösteren testin ÖNCE başarısız SONRA başarılı olmasıyla kanıtlanır. Yalnız "şimdi
geçiyor" demek, testin hatayı hiç yakalamadığı durumu (fail-to-fail) gizler ve bu,
yanlış başarının en yaygın kaynağıdır.

Bu modül yeni komut ÇALIŞTIRMAZ: turda gerçekten yapılmış araç çağrılarının
kaydına bakar (`ToolUse`). Doğrulayıcının kendi komut çalıştırması, kanıtı ölçmek
yerine üretmek olurdu.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...core.evidence import CriterionEvidence, EvidenceStatus, ToolUse
from ...core.execution_plan import VerificationCheck

#: Kanıt metni tek yerde tutulur: durum değişse de sözleşme aynı cümleyle anlatılır.
_KIRMIZI_YOK = "önce kırmızı görülmedi; testin hatayı yakaladığı kanıtlanmadı"
_KIRMIZI_SONRA_YESIL = "önce kırmızı, sonra yeşil: düzeltme kanıtlandı"
_HALA_KIRMIZI = "test hâlâ kırmızı"
_HIC_CALISMADI = "reprodüksiyon testi bu turda hiç çalıştırılmadı"


def evaluate_reproduction(
    check: VerificationCheck,
    *,
    tool_uses: Sequence[ToolUse],
) -> CriterionEvidence:
    """Reprodüksiyon kontrolünü turun gerçek komut kayıtlarından değerlendir."""
    sonuclar = [use.ok for use in tool_uses if _ayni_komut(use, check.target)]
    if not sonuclar:
        return _kanit(check, EvidenceStatus.UNVERIFIED, _HIC_CALISMADI)
    if sonuclar[-1] is False:
        return _kanit(check, EvidenceStatus.FAILED, _HALA_KIRMIZI)
    # Son koşu yeşil: kırmızıdan geldiyse kanıt tamamdır, gelmediyse eksiktir.
    if any(sonuc is False for sonuc in sonuclar[:-1]):
        return _kanit(check, EvidenceStatus.PASSED, _KIRMIZI_SONRA_YESIL)
    return _kanit(check, EvidenceStatus.UNVERIFIED, _KIRMIZI_YOK)


def _ayni_komut(use: ToolUse, target: str) -> bool:
    """Araç kaydı bu kontrolün komutunu mu çalıştırmış?"""
    komut = use.arguments.get("command")
    return isinstance(komut, str) and komut.strip() == target.strip()


def _kanit(check: VerificationCheck, status: EvidenceStatus, ozet: str) -> CriterionEvidence:
    return CriterionEvidence(
        criterion_id=check.criterion_id,
        kind=check.kind,
        status=status,
        summary=ozet,
        command=check.target,
    )

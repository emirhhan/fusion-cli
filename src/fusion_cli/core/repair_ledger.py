"""Yapılandırılmış başarısız denemeleri sohbet bağlamından bağımsız izler.

Bütçe üretmez veya tüketmez; kalan hak mevcut bütçe otoritesinden gelir.
Üretim araçları ve motor bağlantısı bu saf sözleşmenin kapsamı dışındadır.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .failure_identity import failure_identity


class FailureOrigin(Enum):
    """Ürün kusuru ile ölçüm/sağlayıcı kesintisini ayırır."""

    PRODUCT = "product"
    INFRASTRUCTURE = "infrastructure"
    PROVIDER = "provider"


@dataclass(frozen=True, slots=True, order=True)
class SourceFingerprint:
    """Yalnız ilgili kaynak kimliği ve içerik özeti; kaynak metni tutulmaz."""

    path: str
    digest: str

    def __post_init__(self) -> None:
        if not self.path.strip() or not self.digest.strip():
            raise ValueError("Kaynak yolu ve parmak izi boş olamaz.")


@dataclass(frozen=True, slots=True)
class FailureEvidence:
    """Araçtan gelen hata ailesi ve bağımsız deneme kanıtı."""

    check_id: str
    family: str
    attempt_id: str
    sources: tuple[SourceFingerprint, ...] = ()
    origin: FailureOrigin = FailureOrigin.PRODUCT

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.check_id, self.family, self.attempt_id)):
            raise ValueError("Kontrol, hata ailesi ve deneme kimliği boş olamaz.")
        for name in ("check_id", "family", "attempt_id"):
            object.__setattr__(self, name, failure_identity(getattr(self, name)))
        if len({source.path for source in self.sources}) != len(self.sources):
            raise ValueError("İlgili kaynak yolları benzersiz olmalı.")


class RepairAction(Enum):
    """Karar başarı iddiası değil, sonraki onarım hareketidir."""

    REPAIR = "repair"
    CHANGE_APPROACH = "change_approach"
    EXHAUSTED = "exhausted"
    ALREADY_OBSERVED = "already_observed"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class RepairDecision:
    """Kısa bağlam notu ve ilgili kaynak değişimi kanıtı."""

    action: RepairAction
    has_source_change: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class RepairSnapshot:
    """Bağlam sıkıştırması veya iç içe tur için bağımsız kayıt."""

    failures: tuple[FailureEvidence, ...] = ()


class RepairLedger:
    """Bir kullanıcı turunun mevcut bütçesine bağlı onarım kanıtı kaydı."""

    def __init__(self, snapshot: RepairSnapshot | None = None) -> None:
        self._failures = list(snapshot.failures if snapshot is not None else ())

    def snapshot(self) -> RepairSnapshot:
        """Kaynak içerikleri veya geçmiş sohbet olmadan kaydı aktar."""
        return RepairSnapshot(tuple(self._failures))

    def observe(self, evidence: FailureEvidence, *, remaining_repairs: int) -> RepairDecision:
        """Aynı ölçümün sorgusunu ayır; bütçe hakkını başka yerde tüket."""
        if remaining_repairs < 0:
            raise ValueError("Kalan onarım hakkı negatif olamaz.")
        if evidence.origin is not FailureOrigin.PRODUCT:
            return RepairDecision(RepairAction.EXCLUDED)
        if any(self._attempt_key(item) == self._attempt_key(evidence) for item in self._failures):
            return RepairDecision(RepairAction.ALREADY_OBSERVED)
        previous = next(
            (
                item
                for item in reversed(self._failures)
                if item.check_id == evidence.check_id and item.family == evidence.family
            ),
            None,
        )
        self._failures.append(evidence)
        known = previous is not None and bool(previous.sources) and bool(evidence.sources)
        changed = (
            known and previous is not None and sorted(previous.sources) != sorted(evidence.sources)
        )
        if remaining_repairs == 0:
            return RepairDecision(
                RepairAction.EXHAUSTED, changed, "Onarım bütçesi tükendi; sonuç doğrulanmadı."
            )
        if previous is not None:
            source_note = (
                "ilgili kaynak değişti"
                if changed
                else "ilgili kaynak aynı"
                if known
                else "kaynak değişimi bilinmiyor"
            )
            return RepairDecision(
                RepairAction.CHANGE_APPROACH,
                has_source_change=changed,
                note=(
                    f"{evidence.check_id}/{evidence.family}: {source_note}; "
                    "aynı hata ailesi gerçek ölçümde sürüyor. "
                    "kök nedeni yeniden incele; yaklaşımı değiştir."
                ),
            )
        return RepairDecision(RepairAction.REPAIR, changed)

    @staticmethod
    def _attempt_key(evidence: FailureEvidence) -> tuple[str, str, str]:
        return evidence.check_id, evidence.family, evidence.attempt_id

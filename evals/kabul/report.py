"""Kabul koşusu kayıtlarını JSON'a ve alan başına özete çevirir."""

from __future__ import annotations

import dataclasses
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from evals.kabul.model import Outcome, RunRecord
from evals.kabul.preflight import PreflightReport


@dataclass(frozen=True, slots=True)
class AreaSummary:
    """Bir alanın koşu özetleri; geçersiz koşular orana girmez."""

    area: str
    outcomes: dict[str, int]
    measured: int
    passed: int
    false_success: int
    mean_check_ratio: float

    @property
    def pass_rate(self) -> float:
        return self.passed / self.measured if self.measured else 0.0


def summarize(records: Sequence[RunRecord]) -> list[AreaSummary]:
    """Alan başına sonuç dağılımı ve geçen madde oranı."""
    ozetler = []
    for alan in sorted({kayit.area for kayit in records}):
        kayitlar = [k for k in records if k.area == alan]
        olculen = [k for k in kayitlar if k.outcome is not Outcome.INVALID]
        oranlar = [
            k.inspection.passed_count / len(k.inspection.checks)
            for k in olculen
            if k.inspection.checks
        ]
        ozetler.append(
            AreaSummary(
                area=alan,
                outcomes=dict(Counter(k.outcome.value for k in kayitlar)),
                measured=len(olculen),
                passed=sum(1 for k in olculen if k.outcome is Outcome.PASSED),
                false_success=sum(1 for k in olculen if k.false_success),
                mean_check_ratio=round(sum(oranlar) / len(oranlar), 3) if oranlar else 0.0,
            )
        )
    return ozetler


def write_report(
    path: Path, records: Sequence[RunRecord], preflight: PreflightReport | None
) -> None:
    """Ham kayıtları ve özetleri tek JSON dosyasına yaz."""
    veri = {
        "on_kontrol": dataclasses.asdict(preflight) if preflight else None,
        "ozet": [dataclasses.asdict(ozet) for ozet in summarize(records)],
        "kosular": [_record_payload(kayit) for kayit in records],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(veri, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _record_payload(record: RunRecord) -> dict[str, object]:
    payload = dataclasses.asdict(record)
    if record.comparison is None:
        del payload["comparison"]
    return payload


def _comparison_text(record: RunRecord) -> str:
    proof = record.comparison
    if proof is None:
        return ""
    return (
        f" | karşılaştırma: import {'doğrulandı' if proof.import_verified else 'doğrulanmadı'}, "
        f"config {'doğrulandı' if proof.config_verified else 'doğrulanmadı'}; "
        "eş koşullar bilinmiyor (auth/cache/context/kaynak), %90 kanıtı yok"
    )


def render_text(records: Sequence[RunRecord]) -> str:
    """Terminal için kısa özet: alan, sonuç dağılımı, madde oranı, düşen maddeler."""
    satirlar = []
    for ozet in summarize(records):
        satirlar.append(
            f"{ozet.area}: {ozet.outcomes} | ölçülen {ozet.measured}, geçen {ozet.passed}, "
            f"sahte başarı {ozet.false_success}, madde oranı {ozet.mean_check_ratio:.0%}"
        )
        for kayit in (k for k in records if k.area == ozet.area):
            dusen = [c.name for c in kayit.inspection.checks if not c.passed]
            neden = kayit.inspection.invalid_reason or kayit.driver_error
            satirlar.append(
                f"  #{kayit.attempt} {kayit.outcome.value} "
                f"{kayit.metrics.elapsed_s:.0f} sn, {kayit.metrics.model_calls} çağrı"
                + (f" | düşen: {', '.join(dusen)}" if dusen else "")
                + (f" | neden: {neden[:160]}" if neden else "")
                + _comparison_text(kayit)
            )
    return "\n".join(satirlar)

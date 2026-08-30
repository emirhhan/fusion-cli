"""Oturum boyunca biriken kullanım ve sağlık özeti.

Ayarlar ekranı "ne kadar harcadım, sistem sağlıklı mı" sorusunu cevaplamalı.
Rakamlar UYDURULMAZ: token sayıları ve maliyet sağlayıcı sınırında hesaplanıp
`ModelCallFinished` olayıyla gelen `TokenUsage`'tan toplanır (bkz.
`core/types.py::TokenUsage`), güvenilirlik ise `HealthRegistry`'den okunur.

Sayaç OTURUM ÖMÜRLÜDÜR ve diske yazılmaz: kalıcı bir kullanım kaydı tutmak
kullanıcının hangi modele ne sorduğunun geçmişini biriktirmek olurdu; bunun
için açık bir talep yok.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.events import Event, ModelCallFinished
from ..core.health import CircuitPhase, HealthRegistry
from ..core.types import TokenUsage


@dataclass
class UsageMeter:
    """Model çağrılarının token ve maliyet toplamı."""

    #: Arka plan çağrıları (hakem, sentez) DAHİLDİR: kotadan onlar da harcar.
    total: TokenUsage = field(default_factory=TokenUsage)
    calls: int = 0
    by_model: dict[str, TokenUsage] = field(default_factory=dict)

    def observe(self, event: Event) -> None:
        """Olay bir model çağrısının bitişiyse tüketimi topla."""
        if not isinstance(event, ModelCallFinished):
            return
        usage = getattr(event.result, "usage", None)
        if usage is None:
            return
        model = str(getattr(event.result, "model", "") or "bilinmeyen")
        self.total = self.total + usage
        self.calls += 1
        self.by_model[model] = self.by_model.get(model, TokenUsage()) + usage

    def payload(self) -> dict[str, Any]:
        return {
            "cagri": self.calls,
            "girdi_token": self.total.prompt_tokens,
            "cikti_token": self.total.completion_tokens,
            "toplam_token": self.total.total_tokens,
            "maliyet_usd": round(self.total.cost_usd, 6),
            "modeller": [
                {
                    "model": model,
                    "toplam_token": usage.total_tokens,
                    "maliyet_usd": round(usage.cost_usd, 6),
                }
                for model, usage in sorted(
                    self.by_model.items(), key=lambda item: -item[1].total_tokens
                )
            ],
        }


#: Devre durumlarının kullanıcıya görünen karşılığı.
_FAZ_METNI = {
    CircuitPhase.CLOSED: "sağlıklı",
    CircuitPhase.OPEN: "geçici olarak kapalı",
    CircuitPhase.HALF_OPEN: "yeniden deneniyor",
}


def health_payload(health: HealthRegistry | None) -> list[dict[str, Any]]:
    """Model başına güvenilirlik özeti.

    Hiç örnek görülmemiş model listelenmez: "0 örnekle %0 güvenilir" demek,
    ölçülmemiş bir şeyi kötü göstermek olurdu.
    """
    rows: list[dict[str, Any]] = []
    if health is None:
        return rows
    for model, durum in health.snapshot():
        if durum.samples == 0:
            continue
        rows.append(
            {
                "model": model,
                "durum": _FAZ_METNI.get(durum.phase, "bilinmiyor"),
                "skor": round(durum.score, 3),
                "ornek": durum.samples,
                "gecikme_ms": round(durum.avg_latency_ms),
            }
        )
    return rows


def usage_status(meter: UsageMeter, health: HealthRegistry | None) -> dict[str, Any]:
    """`kullanim.durum`: bu oturumun tüketimi ve model sağlığı."""
    return {"ok": True, "kullanim": meter.payload(), "saglik": health_payload(health)}

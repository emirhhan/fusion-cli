"""Oturum boyunca biriken kullanım ve sağlık özeti.

Ayarlar ekranı "ne kadar harcadım, sistem sağlıklı mı" sorusunu cevaplamalı.
Rakamlar UYDURULMAZ: token sayıları ve maliyet sağlayıcı sınırında hesaplanıp
`ModelCallFinished` olayıyla gelen `TokenUsage`'tan toplanır (bkz.
`core/types.py::TokenUsage`), güvenilirlik ise `HealthRegistry`'den okunur.

Sayaç OTURUM ÖMÜRLÜDÜR ve diske yazılmaz. Kalıcı pencereler (24s/7g/30g) ayrı bir
günlükten gelir (`observability/usage_log.py`, P-056): o günlük yalnız sayıları tutar,
istem metni yazmaz ve `runtime.usage_log: false` ile kapatılır.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ..core.events import Event, ModelCallAbandoned, ModelCallFinished
from ..core.health import CircuitPhase, HealthRegistry
from ..core.types import TokenUsage
from ..observability.usage_log import UsageLog, summarize


@dataclass
class UsageMeter:
    """Model çağrılarının token ve maliyet toplamı."""

    #: Arka plan çağrıları (hakem, sentez) DAHİLDİR: kotadan onlar da harcar.
    total: TokenUsage = field(default_factory=TokenUsage)
    calls: int = 0
    #: Yanıt gelmeden iptal edilen çağrılar ve ölçümü eksik gelenler: tüketimleri
    #: BİLİNMİYOR, sıfır sayılmaz (bkz. `ModelCallAbandoned`). Toplam alt sınırdır.
    uncertain_calls: int = 0
    by_model: dict[str, TokenUsage] = field(default_factory=dict)
    last_agent_prompt_tokens: int | None = None
    last_agent_model: str | None = None

    def observe(self, event: Event) -> None:
        """Olay bir model çağrısının bitişiyse tüketimi topla."""
        if isinstance(event, ModelCallAbandoned):
            self.uncertain_calls += 1
            return
        if not isinstance(event, ModelCallFinished):
            return
        usage = getattr(event.result, "usage", None)
        if usage is None:
            return
        model = str(getattr(event.result, "model", "") or "bilinmeyen")
        self.total = self.total + usage
        self.calls += 1
        if usage.completeness != "complete":
            self.uncertain_calls += 1
        self.by_model[model] = self.by_model.get(model, TokenUsage()) + usage
        if (
            event.role == "agent"
            and not event.background
            and event.result.ok
            and usage.prompt_tokens > 0
        ):
            self.last_agent_prompt_tokens = usage.prompt_tokens
            self.last_agent_model = model

    def payload(self) -> dict[str, Any]:
        return {
            "cagri": self.calls,
            "girdi_token": self.total.prompt_tokens,
            "cikti_token": self.total.completion_tokens,
            "toplam_token": self.total.total_tokens,
            "maliyet_usd": round(self.total.cost_usd, 6),
            "belirsiz_cagri": self.uncertain_calls,
            "maliyet_tam": self.uncertain_calls == 0,
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


def limits_payload(
    per_minute: Mapping[str, float] | None, health: HealthRegistry | None
) -> dict[str, Any]:
    """Kota/limit göstergesi (P-066): yalnız ÖLÇÜLEN ya da AYARLANAN şeyler.

    Claude Code'un plan çubuklarının karşılığı burada abonelik kotası DEĞİLDİR: web
    sağlayıcıları (ChatGPT, Claude…) kalan kotayı dışarı vermez, uydurulmaz. Gösterilen
    iki gerçek veri: yapılandırmadaki dakikalık istek sınırı (`rate_limit_per_minute`,
    süreçler arası paylaşılan kova) ve sağlayıcının o an kota bekletip bekletmediği
    (sağlık kaydındaki 429 serisi + devrenin yeniden deneme süresi).

    Ölçüldü (31 Ekim): `kullanim.durum` yalnız oturum sayacı ve sağlık fazını taşıyordu;
    "sağlayıcı beni bekletiyor mu, ne kadar" sorusunun cevabı arayüzde yoktu.
    """
    limits = [
        {"saglayici": provider, "dakikaLimiti": float(limit)}
        for provider, limit in sorted((per_minute or {}).items())
        if float(limit) > 0
    ]
    waiting: list[dict[str, Any]] = []
    if health is not None:
        for model, durum in health.snapshot():
            if durum.rate_limit_streak <= 0:
                continue
            waiting.append(
                {
                    "model": model,
                    "seri": durum.rate_limit_streak,
                    "yenidenSn": round(durum.retry_in_s),
                }
            )
    return {"dakikaLimitleri": limits, "kotaBekleyen": waiting}


def usage_status(
    meter: UsageMeter,
    health: HealthRegistry | None,
    per_minute: Mapping[str, float] | None = None,
    *,
    usage_log: UsageLog | None = None,
) -> dict[str, Any]:
    """`kullanim.durum`: bu oturumun tüketimi, model sağlığı, limit göstergesi ve
    (günlük açıksa) pencereler.

    `gecmis` 24s/7g/30g toplamlarını, `atif` 7 günlük kırılımı (ana/alt ajan, arka plan,
    MCP sunucusu, beceri) taşır. Günlük kapalıysa ikisi de boş; sayaç değişmez (P-056).
    `limitler` yalnız ölçülen/ayarlanan sınırları taşır (P-066).
    """
    payload: dict[str, Any] = {
        "ok": True,
        "kullanim": meter.payload(),
        "saglik": health_payload(health),
        "limitler": limits_payload(per_minute, health),
        "gecmis": [],
        "atif": {"kaynaklar": [], "mcp": [], "beceriler": []},
        "gunluk_acik": usage_log is not None,
    }
    if usage_log is None:
        return payload
    summary = summarize(usage_log.read(), now=time.time(), session_id=usage_log.session_id)
    payload["gecmis"] = [
        {
            "pencere": label,
            "cagri": bucket.calls,
            "toplam_token": bucket.usage.total_tokens,
            "maliyet_usd": round(bucket.usage.cost_usd, 6),
            "maliyet_tam": bucket.cost_complete,
        }
        for label, bucket in summary.windows[1:]
    ]
    payload["atif"] = {
        "pencere": summary.window_label,
        "kaynaklar": [
            {
                "ad": row.label,
                "cagri": row.calls,
                "toplam_token": row.tokens,
                "maliyet_usd": round(row.cost_usd, 6),
            }
            for row in summary.by_actor
        ],
        "mcp": [{"ad": server, "cagri": count} for server, count in summary.mcp_calls],
        "beceriler": [{"ad": skill, "cagri": count} for skill, count in summary.skills],
    }
    return payload

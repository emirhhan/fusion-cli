"""Gateway analytics — istek/token/gecikme telemetrisi ve son istek günlüğü.

Oturum boyunca biriken sayaçlar; uzak sunucu değil, yerel panelde gösterilir. Saf
(ağ yok) ve test edilebilir. Kişisel veri tutmaz: yalnızca model adı, token sayısı,
gecikme ve başarı bayrağı — istek/yanıt METNİ saklanmaz.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RequestRecord:
    """Tek bir isteğin özeti (metin YOK)."""

    requested_model: str
    served_model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    ok: bool
    cached: bool = False


class Analytics:
    """Gateway'in canlı kullanım istatistikleri."""

    def __init__(self, *, log_size: int = 50, latency_window: int = 500) -> None:
        self.requests = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cache_hits = 0
        self.compression_saved_chars = 0
        self._latencies: deque[int] = deque(maxlen=latency_window)
        self._log: deque[RequestRecord] = deque(maxlen=log_size)
        self._per_model: dict[str, dict[str, int]] = {}

    def record(self, record: RequestRecord) -> None:
        self.requests += 1
        self.prompt_tokens += record.prompt_tokens
        self.completion_tokens += record.completion_tokens
        if record.cached:
            self.cache_hits += 1
        if record.latency_ms > 0:
            self._latencies.append(record.latency_ms)
        stats = self._per_model.setdefault(
            record.served_model, {"requests": 0, "tokens": 0, "latency_sum": 0}
        )
        stats["requests"] += 1
        stats["tokens"] += record.prompt_tokens + record.completion_tokens
        stats["latency_sum"] += record.latency_ms
        self._log.appendleft(record)

    def add_compression_saving(self, saved_chars: int) -> None:
        if saved_chars > 0:
            self.compression_saved_chars += saved_chars

    def _avg_latency(self) -> int:
        return round(sum(self._latencies) / len(self._latencies)) if self._latencies else 0

    def _p95_latency(self) -> int:
        if not self._latencies:
            return 0
        ordered = sorted(self._latencies)
        index = min(len(ordered) - 1, int(0.95 * len(ordered)))
        return ordered[index]

    def snapshot(self) -> dict[str, Any]:
        """Panelin gösterdiği özet + son istekler + model başına dağılım."""
        return {
            "requests": self.requests,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "avg_latency_ms": self._avg_latency(),
            "p95_latency_ms": self._p95_latency(),
            "cache_hits": self.cache_hits,
            "compression_saved_chars": self.compression_saved_chars,
            "per_model": [
                {
                    "model": model,
                    "requests": stats["requests"],
                    "tokens": stats["tokens"],
                    "avg_latency_ms": round(stats["latency_sum"] / stats["requests"])
                    if stats["requests"]
                    else 0,
                }
                for model, stats in sorted(
                    self._per_model.items(), key=lambda kv: -kv[1]["requests"]
                )
            ],
            "recent": [
                {
                    "requested": rec.requested_model,
                    "served": rec.served_model,
                    "tokens": rec.prompt_tokens + rec.completion_tokens,
                    "latency_ms": rec.latency_ms,
                    "ok": rec.ok,
                    "cached": rec.cached,
                }
                for rec in self._log
            ],
        }

"""Model performans belleği — fusion motorunun öz-öğrenmesi.

Her fusion turunda her adayın puanı, gecikmesi ve kazanıp kazanmadığı yazılır.
Bir sonraki turda aday sıralaması bu geçmişe göre değişir: kapalı bir öğrenme döngüsü.

Seçim ölçütü **ortalama puan − hafif gecikme cezası**dır. Ceza üst sınırlıdır
(`MAX_LATENCY_PENALTY`): hız kaliteyi ezmemeli, yalnızca eşit kalitede tercih sebebi
olmalıdır.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..core.clock import SystemClock
from ..core.memory import Feedback, ModelStats, Outcome
from ..core.protocols import Clock
from .store import get_collection

COLLECTION = "model_performance"

#: Gecikme cezasının üst sınırı. Puan 0..1 aralığındadır; ceza en fazla 0.1 olabilir.
MAX_LATENCY_PENALTY = 0.1
#: Cezanın doygunluğa ulaştığı gecikme (ms). 60 sn ve üstü aynı cezayı alır.
LATENCY_SATURATION_MS = 60_000.0


class ChromaPerformanceMemory:
    """ChromaDB destekli performans belleği."""

    def __init__(self, directory: Path, *, clock: Clock | None = None) -> None:
        self._collection = get_collection(directory, COLLECTION)
        self._clock = clock or SystemClock()

    def record(self, outcome: Outcome) -> None:
        self._collection.add(
            ids=[uuid.uuid4().hex],
            documents=[outcome.task],
            metadatas=[
                {
                    "task_type": outcome.task_type,
                    "model_name": outcome.model_name,
                    "score": float(outcome.score),
                    "latency_ms": int(outcome.latency_ms),
                    "tokens": int(outcome.tokens),
                    "won": bool(outcome.won),
                    "timestamp": self._clock.now(),
                }
            ],
        )

    def best_model(self, task_type: str) -> str | None:
        rows = self._collection.get(where={"task_type": task_type})
        metadatas = rows.get("metadatas") or []
        if not metadatas:
            return None

        scores: dict[str, list[float]] = defaultdict(list)
        latencies: dict[str, list[float]] = defaultdict(list)
        for meta in metadatas:
            scores[str(meta["model_name"])].append(float(meta["score"]))
            latencies[str(meta["model_name"])].append(float(meta["latency_ms"]))

        ranked = {name: _adjusted_score(values, latencies[name]) for name, values in scores.items()}
        return max(ranked, key=lambda name: ranked[name]) if ranked else None

    def apply_feedback(self, task_type: str, model_name: str, feedback: Feedback) -> int:
        rows = self._collection.get(
            where={"$and": [{"task_type": task_type}, {"model_name": model_name}]}
        )
        ids = rows.get("ids") or []
        if not ids:
            return 0

        metadatas = rows.get("metadatas") or []
        documents = rows.get("documents") or []
        # En YENİ kaydı hedefle: geri bildirim son çalıştırmaya aittir.
        newest = max(range(len(ids)), key=lambda index: metadatas[index].get("timestamp", 0))

        updated = dict(metadatas[newest])
        updated["score"] = _clamp(float(updated["score"]) + feedback.delta)
        updated["feedback"] = feedback.value
        self._collection.update(
            ids=[ids[newest]], documents=[documents[newest]], metadatas=[updated]
        )
        return 1

    def stats(self) -> tuple[ModelStats, ...]:
        metadatas = self._collection.get().get("metadatas") or []
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for meta in metadatas:
            grouped[str(meta["model_name"])].append(meta)

        rows = [_summarize(name, records) for name, records in grouped.items()]
        return tuple(sorted(rows, key=lambda row: row.avg_score, reverse=True))


def _adjusted_score(scores: list[float], latencies: list[float]) -> float:
    """Ortalama puandan hafif gecikme cezası düş."""
    average = sum(scores) / len(scores)
    mean_latency = sum(latencies) / len(latencies)
    penalty = min(mean_latency / LATENCY_SATURATION_MS, 1.0) * MAX_LATENCY_PENALTY
    return average - penalty


def _summarize(name: str, records: list[dict[str, Any]]) -> ModelStats:
    count = len(records)
    return ModelStats(
        model=name,
        samples=count,
        avg_score=round(sum(float(r["score"]) for r in records) / count, 3),
        wins=sum(1 for r in records if r.get("won")),
        avg_latency_ms=int(sum(float(r["latency_ms"]) for r in records) / count),
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

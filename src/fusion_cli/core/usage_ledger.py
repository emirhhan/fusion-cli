"""Bir turun çağrı kimliğiyle tekilleştirilmiş, gözlenen kullanım alt sınırı."""

from __future__ import annotations

from dataclasses import dataclass

from .types import TokenUsage


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    unknown_calls: int
    total_calls: int
    cost_known: bool


class UsageLedger:
    """Yanıt gelmeyen/ölçülmeyen çağrı sıfır tüketim sayılmaz."""

    def __init__(self) -> None:
        self._calls: dict[int, TokenUsage | None] = {}

    def reserve(self, call_id: int) -> None:
        self._calls.setdefault(call_id, None)

    def record(self, call_id: int, usage: TokenUsage) -> None:
        """Bir çağrının ilk ölçümünü kaydet; replay tüketimi katlamaz."""
        self.reserve(call_id)
        if self._calls[call_id] is None:
            self._calls[call_id] = usage

    def snapshot(self) -> UsageSnapshot:
        values = tuple(self._calls.values())
        known = [usage for usage in values if usage is not None]
        return UsageSnapshot(
            prompt_tokens=sum(usage.prompt_tokens for usage in known if usage.prompt_measured),
            completion_tokens=sum(
                usage.completion_tokens for usage in known if usage.completion_measured
            ),
            cost_usd=sum(usage.cost_usd for usage in known if usage.cost_known),
            unknown_calls=sum(
                usage is None or usage.completeness != "complete" for usage in values
            ),
            total_calls=len(values),
            cost_known=bool(values)
            and all(usage is not None and usage.cost_known for usage in values),
        )

"""Oturum maliyeti ve token takibi.

Bir dinleyicidir: olay veriyolundaki `ModelCallFinished` olaylarını dinler ve
toplar. Bu sayede **her** model çağrısı sayıma girer — aday, hakem, sentez,
öz-denetim, ders çıkarımı, alt-ajan. Eski projede toplama birden çok yerde
yapıldığı için bazı çağrı yolları sessizce sayıma girmiyordu; tek dinleyici bu
sınıf hatayı yapısal olarak imkânsız kılar.

Maliyet hesaplanmaz, yalnızca toplanır: hesap sağlayıcı sınırında yapılmıştır.
"""

from __future__ import annotations

from collections import defaultdict

from ..core.events import Event, ModelCallFinished
from ..core.types import TokenUsage


class CostTracker:
    """Oturum boyunca token ve maliyet biriktiren dinleyici."""

    def __init__(self) -> None:
        self._by_role: dict[str, TokenUsage] = defaultdict(TokenUsage)
        self._calls: dict[str, int] = defaultdict(int)
        self._failed_calls = 0

    def handle(self, event: Event) -> None:
        if not isinstance(event, ModelCallFinished):
            return
        if not event.result.ok:
            self._failed_calls += 1
            return
        self._by_role[event.role] = self._by_role[event.role] + event.result.usage
        self._calls[event.role] += 1

    @property
    def total(self) -> TokenUsage:
        """Tüm rollerin toplamı."""
        combined = TokenUsage()
        for usage in self._by_role.values():
            combined = combined + usage
        return combined

    @property
    def calls(self) -> int:
        return sum(self._calls.values())

    @property
    def failed_calls(self) -> int:
        return self._failed_calls

    def by_role(self) -> tuple[tuple[str, int, TokenUsage], ...]:
        """(rol, çağrı sayısı, kullanım) satırları — token toplamına göre azalan."""
        rows = tuple((role, self._calls[role], usage) for role, usage in self._by_role.items())
        return tuple(sorted(rows, key=lambda row: row[2].total_tokens, reverse=True))

    def reset(self) -> None:
        self._by_role.clear()
        self._calls.clear()
        self._failed_calls = 0

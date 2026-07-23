"""Dış dünyaya bakan yeteneklerin sözleşmeleri.

Concrete sınıf iş mantığına gömülmez; motorlar yalnızca bu protokolleri görür.
Böylece sağlayıcı değiştirmek ya da testte sahte vermek imza değişikliği gerektirmez.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from .types import CompletionRequest, ModelResult, StreamItem


class LlmProvider(Protocol):
    """Bir LLM'e çağrı yapabilen her şey.

    Uygulamalar hata FIRLATMAZ: kurtarılamayan durumda `ok=False` sonuç döner.
    """

    @property
    def label(self) -> str:
        """Teşhis ve olaylarda kullanılan okunur ad."""
        ...

    async def complete(self, request: CompletionRequest) -> ModelResult:
        """İsteği çalıştır ve toparlanmış sonucu döndür."""
        ...

    def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        """İsteği akıtarak çalıştır. Akış daima tek bir `StreamDone` ile biter."""
        ...


class Clock(Protocol):
    """Zaman kaynağı. Testte sahte zaman verilebilmesi için soyutlanmıştır."""

    def monotonic(self) -> float:
        """Süre ölçümü için monoton saniye."""
        ...

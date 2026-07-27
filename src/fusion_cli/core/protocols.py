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

    def now(self) -> float:
        """Duvar saati zaman damgası (Unix epoch saniyesi)."""
        ...


class Sleeper(Protocol):
    """Beklemeyi yapan şey. `Clock`'tan AYRIDIR: o zamanı okur, bu zaman geçirir.

    Soyut olmak zorunda: yeniden deneme gecikmeleri 34 ve 68 saniyedir ve testin
    bunları gerçekten beklemesi kabul edilemez — sahte uyutucu beklemeyi kaydeder,
    geçirmez. Aynı sebeple gecikmeler koda gömülmez, yapılandırmadan gelir.
    """

    async def sleep(self, seconds: float) -> None:
        """Verilen süre kadar bekle."""
        ...

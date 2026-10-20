"""Anahtar döndüren sağlayıcı — çok-hesap havuzunu tek modele bağlar.

Bir çağrı için havuzdan bir anahtar seçilir; sonuç HIZ SINIRI (429) ise o anahtar
cooldown'a alınır ve İSTEK ANINDA havuzun bir sonraki anahtarıyla yeniden denenir.
Böylece bir hesabın dolması ötekini bekletmez. Havuz tükenirse (hepsi cooldown'da)
son sonuç döner ve dıştaki fallback/retry devreye girer.

Kompozisyondaki yeri en içtedir (model = LiteLlmProvider). Anahtar rotasyonu MODEL
düzeyinde olur; yeniden-deneme ve circuit breaker bunun DIŞINDA çalışır.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

from ..core.protocols import LlmProvider
from ..core.types import (
    CompletionRequest,
    ModelResult,
    StreamDone,
    StreamItem,
    is_rate_limit_error,
)
from .key_pool import KeyPool

#: Bir anahtarla sağlayıcı üreten fabrika (LiteLlmProvider(model, …, api_key=key)).
KeyedProviderFactory = Callable[[str], LlmProvider]


class KeyRotatingProvider:
    """Havuzdaki anahtarlar arasında dönen sağlayıcı."""

    def __init__(self, factory: KeyedProviderFactory, pool: KeyPool, *, label: str) -> None:
        self._factory = factory
        self._pool = pool
        self._label = label

    @property
    def label(self) -> str:
        return self._label

    def _fallback_key(self) -> str:
        # Hepsi cooldown'da: cooldown sezgiseldir, yine de ilk anahtarla dene.
        return self._pool.any_key() or ""

    async def complete(self, request: CompletionRequest) -> ModelResult:
        result: ModelResult | None = None
        # En fazla havuz boyu kadar farklı anahtar dene.
        for _ in range(max(1, self._pool.size)):
            key = self._pool.pick()
            if key is None:
                break
            result = await self._factory(key).complete(request)
            if not is_rate_limit_error(result.error):
                return result
            self._pool.mark_rate_limited(key)
        if result is not None:
            return result
        # Havuzda kullanılabilir anahtar kalmadı: son çare, ilk anahtarla dene.
        return await self._factory(self._fallback_key()).complete(request)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        # Akışta rotasyon tek seçimdir: bir anahtarla akıtılır; açılışta 429 gelirse
        # o anahtar cooldown'a alınır ve bir sonrakiyle yeniden AÇILIR (metin akmadan).
        for _ in range(max(1, self._pool.size)):
            key = self._pool.pick()
            if key is None:
                break
            inner = self._factory(key)
            stream = inner.stream(request)
            first = await anext(stream, None)
            if first is None:
                continue
            if isinstance(first, StreamDone) and is_rate_limit_error(first.result.error):
                self._pool.mark_rate_limited(key)
                await _close(stream)
                continue
            yield first
            async for item in stream:
                yield item
            return
        # Anahtar kalmadı: son çare tek akış.
        async for item in self._factory(self._fallback_key()).stream(request):
            yield item


async def _close(stream: AsyncIterator[StreamItem]) -> None:
    closer = getattr(stream, "aclose", None)
    if closer is None:
        return
    try:
        await closer()
    except Exception:
        return

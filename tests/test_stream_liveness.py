"""Canlılık parçaları Retrying ve Fallback arkasında kaybolmaz (P1-05).

Ölçüldü (29 Ekim): `first_meaningful` boş geçici parçaları tüketip atıyordu; yalnızca
araç çağrısından oluşan uzun yanıtta üst katman tek bir canlılık parçası görmüyordu.
"""

from __future__ import annotations

from fusion_cli.core.types import CompletionRequest, Message, ModelResult, StreamDone, TextChunk
from fusion_cli.providers.chain import FallbackProvider
from fusion_cli.providers.retrying import RetryingProvider

CANLILIK = TextChunk("", provisional=True)


class _SahteUyutucu:
    async def sleep(self, seconds: float) -> None:
        return None


def _istek() -> CompletionRequest:
    return CompletionRequest(
        messages=(Message("user", "x"),), temperature=0.0, max_tokens=16, timeout_s=5
    )


class _ArgumanYazan:
    """Metin yok; yalnız araç argümanı akar (canlılık parçaları), sonda araç çağrısı."""

    label = "arac-yazan"

    def __init__(self, parca: int = 3, ok: bool = True) -> None:
        self._parca = parca
        self._ok = ok

    async def complete(self, request):  # pragma: no cover
        raise NotImplementedError

    async def stream(self, request):
        for _ in range(self._parca):
            yield CANLILIK
        yield StreamDone(
            ModelResult(name="r", model=self.label, text="tamam", latency_ms=1, ok=self._ok)
        )


def _canlilik_sayisi(items) -> int:
    return sum(1 for item in items if isinstance(item, TextChunk) and item.provisional)


async def test_retrying_canlilik_parcalarini_iletir():
    sarmal = RetryingProvider(_ArgumanYazan(), delays_s=(1.0,), sleeper=_SahteUyutucu())

    items = [item async for item in sarmal.stream(_istek())]

    assert _canlilik_sayisi(items) == 3
    assert isinstance(items[-1], StreamDone)


async def test_fallback_canlilik_parcalarini_iletir():
    zincir = FallbackProvider([_ArgumanYazan(), _ArgumanYazan(2)], role="agent")

    items = [item async for item in zincir.stream(_istek())]

    assert _canlilik_sayisi(items) == 3
    assert isinstance(items[-1], StreamDone)


async def test_fallback_metin_tasiyan_gecici_parca_yine_sizmaz():
    class _Dusunen:
        label = "dusunen"

        async def complete(self, request):  # pragma: no cover
            raise NotImplementedError

        async def stream(self, request):
            yield TextChunk("düşünce", provisional=True)
            yield StreamDone(
                ModelResult(name="r", model="dusunen", text="", latency_ms=1, ok=False, error="x")
            )

    zincir = FallbackProvider([_Dusunen(), _ArgumanYazan(0)], role="agent")

    items = [item async for item in zincir.stream(_istek())]

    assert not any(isinstance(i, TextChunk) and i.text == "düşünce" for i in items)

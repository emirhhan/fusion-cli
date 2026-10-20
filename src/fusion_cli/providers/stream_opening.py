"""Sağlayıcı akışının ilk gerçek çıktısını bul."""

from __future__ import annotations

from collections.abc import AsyncIterator

from ..core.types import StreamItem, TextChunk


async def first_meaningful(stream: AsyncIterator[StreamItem]) -> StreamItem | None:
    """Boş geçici parçalar yanıtın başladığı anlamına gelmez."""
    first = await anext(stream, None)
    while isinstance(first, TextChunk) and first.provisional:
        first = await anext(stream, None)
    return first

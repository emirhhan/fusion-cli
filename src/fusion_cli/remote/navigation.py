"""Telefon dock'u; uygulama seçimi masaüstü kontrol komutlarına dönüşmez."""

from __future__ import annotations

from typing import Protocol


class NavigationHost(Protocol):
    async def list(self) -> dict[str, object]: ...

    async def focus(self, target: dict[str, object]) -> dict[str, object]: ...

"""Yetenek kökenlerini yalnız aynı içerik kanıtıyla birleştir."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .capabilities import Capability


def merge_capability(found: dict[str, Capability], capability: Capability) -> None:
    """Yalnız içeriği aynı olan kaynakları birleştir; farklı sürümleri koru."""
    matches = [item for item in found.values() if item.name == capability.name]
    for existing in matches:
        try:
            identical = existing.path.read_bytes() == capability.path.read_bytes()
        except OSError:
            identical = False
        if identical:
            sources = existing.source.split("+")
            if capability.source not in sources:
                key = next(key for key, item in found.items() if item is existing)
                found[key] = replace(existing, source="+".join([*sources, capability.source]))
            return
    key = capability.name if not matches else str(capability.path.resolve())
    found[key] = capability

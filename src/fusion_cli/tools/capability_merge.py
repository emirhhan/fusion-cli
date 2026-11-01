"""Becerileri içerikle birleştir; ajanlarda yüksek öncelikli tanımı koru."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .capabilities import Capability


def shadow_agent(found: dict[str, Capability], capability: Capability) -> None:
    """Claude proje ajanı kullanıcı tanımını gölgeler; dış kaynak seçimi korunur."""
    if capability.source == "claude":
        for key, existing in found.items():
            if existing.name != capability.name or not {"proje", "ek-kok"}.intersection(
                existing.source.split("+")
            ):
                continue
            if existing.path.resolve() == capability.path.resolve():
                # Ev ve proje aynı kökse bu iki tanım değil, tek dosyanın kaynak takma
                # adlarıdır. Önceki nitelikli kimliğin kaynak sırasını koru.
                found[key] = replace(existing, source=f"claude+{existing.source}")
            return
    merge_capability(found, capability)


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

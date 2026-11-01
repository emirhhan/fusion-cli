"""Becerileri içerikle birleştir; ajanlarda yüksek öncelikli tanımı koru."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .capabilities import Capability

#: Yalnız aynı Claude ajan kapsam ailesi gölgelenir; Codex nitelikli seçimleri ayrıdır.
_AGENT_SCOPE_PRIORITY = {"managed": 0, "cli": 1, "proje": 2, "ek-kok": 2, "claude": 3}


def _scope_priority(source: str) -> int | None:
    priorities = [
        _AGENT_SCOPE_PRIORITY[item] for item in source.split("+") if item in _AGENT_SCOPE_PRIORITY
    ]
    return min(priorities) if priorities else None


def shadow_agent(found: dict[str, Capability], capability: Capability) -> None:
    """Yönetilen > CLI > yakın proje > kullanıcı; dış kaynak seçimleri korunur."""
    priority = _scope_priority(capability.source)
    for key, existing in tuple(found.items()):
        if existing.name != capability.name:
            continue
        if _merge_file_alias(found, key, existing, capability):
            return
        if priority is None:
            # Codex, kurulu repo ve yerleşik tanımlar Claude kapsamlarının ALTINDADIR; aynı
            # ad belirsizlik üretmez, önce taranan (daha öncelikli) tanım kazanır (#38).
            if _identical(existing, capability):
                break
            return
        existing_priority = _scope_priority(existing.source)
        if existing_priority is None:
            continue
        if existing_priority <= priority:
            return
        del found[key]
    merge_capability(found, capability)


def _merge_file_alias(
    found: dict[str, Capability], key: str, existing: Capability, capability: Capability
) -> bool:
    """Aynı dosyanın kaynak takma adı gölgelenmez; dosyasız CLI tanımı ayrı kalır."""
    if existing.inline_prompt is not None or capability.inline_prompt is not None:
        return False
    try:
        is_same_file = existing.path.resolve() == capability.path.resolve()
    except (OSError, RuntimeError):
        return False
    if not is_same_file:
        return False
    sources = list(dict.fromkeys((*existing.source.split("+"), *capability.source.split("+"))))
    if "claude" in sources and "proje" in sources:
        # A1'in ev/proje kimliğinde kullanıcı etiketi önce gelir.
        sources = ["claude", *(source for source in sources if source != "claude")]
    found[key] = replace(existing, source="+".join(sources))
    return True


def _identical(left: Capability, right: Capability) -> bool:
    try:
        return left.path.read_bytes() == right.path.read_bytes()
    except OSError:
        return False


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

"""Kısmi protokol hatasında bağımsız okumayı koruyan hedefli onarım."""

from __future__ import annotations

from ...core.tools import Tool
from ...core.types import Message, ParseWarning

MUTATION_DEFERRED = (
    "Protokol uyarısı: eksik çağrının bağımlılığı bilinmediği için bu değişiklik ertelendi."
)
PARTIAL_REPAIR = (
    "Araç yanıtında protokol uyarısı var: {details}\n"
    "Başarılı çağrılar tamamlandı; bunları tekrar gönderme. "
    "Yalnız bozuk veya ertelenen eksik adımı düzelterek gönder."
)


def mutation_deferral(tool: Tool | None, warnings: tuple[ParseWarning, ...]) -> str | None:
    """Bağımlılığı bilinmeyen eksik adım varsa yalnız güvenli okumaları yürüt."""
    if any(warning.blocks_mutation for warning in warnings) and (tool is None or tool.mutating):
        return MUTATION_DEFERRED
    return None


def partial_repair_note(warnings: tuple[ParseWarning, ...]) -> Message:
    """Başarıları yeniden istemeden yalnız kalan protokol adımını düzelt."""
    details = "; ".join(warning.message for warning in warnings if warning.blocks_mutation)
    return Message("user", PARTIAL_REPAIR.format(details=details), harness_note=True)

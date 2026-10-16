"""MCP kaynak ve sağlık değer sözleşmeleri."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.tools import ToolEffect


@dataclass(slots=True)
class RemoteTool:
    """Uzak bir MCP aracının Fusion'a taşınan tanımı."""

    server: str
    name: str
    description: str
    schema: dict[str, object] = field(default_factory=dict)
    effect: ToolEffect = ToolEffect.REMOTE_WRITE


@dataclass(frozen=True, slots=True)
class McpConnectionStatus:
    """Bir MCP sunucusunun diğerlerinden bağımsız sağlık sonucu."""

    server: str
    state: str
    tool_count: int = 0
    latency_ms: int = 0
    message: str | None = None
    #: Başarısızlık türü (`failures.McpFailureKind` değeri); başarıda None.
    kind: str | None = None
    #: Monotonik gözlem anı; sıfır eski/bilinmeyen gözlem demektir.
    observed_at: float = field(default=0.0, compare=False)
    retry_after_s: float | None = field(default=None, compare=False)

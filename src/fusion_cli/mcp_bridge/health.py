"""MCP başarısızlıklarını sır içermeyen sağlık gözlemine çevir."""

from __future__ import annotations

import time

from ..config.models import McpServerConfig
from .failures import classify_failure
from .types import McpConnectionStatus


def failure_status(
    config: McpServerConfig, error: BaseException, *, latency_ms: int, stderr_tail: str = ""
) -> McpConnectionStatus:
    """Başarısızlığı kullanıcının üzerine eylem yapabileceği duruma çevir."""
    failure = classify_failure(error, config, stderr_tail=stderr_tail)
    return McpConnectionStatus(
        server=config.name,
        state=failure.state,
        latency_ms=latency_ms,
        message=failure.message,
        kind=failure.kind.value,
        observed_at=time.monotonic(),
    )

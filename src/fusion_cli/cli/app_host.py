"""Model/RPC verisinden bağımsız uygulama host bağımlılıkları."""

from __future__ import annotations

from dataclasses import dataclass

from ..engines.agent.remotion_bridge import FrameTransport


@dataclass(frozen=True, slots=True)
class AppHostDependencies:
    """Yalnız composition root tarafından verilen opsiyonel taşıma."""

    remotion_transport: FrameTransport | None = None

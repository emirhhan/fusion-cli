"""Yerel gateway sunucusunu çalıştır — `fusion serve`.

`uvicorn` yalnızca gateway kullanılınca gerekir (`fusion-cli[gateway]` ekstrası).
Kurulu değilse anlaşılır bir hata verilir; ürünün geri kalanı etkilenmez.
Sunucu YALNIZCA yerelde dinler (varsayılan 127.0.0.1) — uzak/paylaşımlı değildir.
"""

from __future__ import annotations

import logging

from ..config.models import Config
from ..core.errors import FusionError
from ..core.health import HealthRegistry
from .app import GatewayApp

#: Varsayılan yerel adres ve port. Koda gömülü sihirli değer değil, gateway sabiti.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

_logger = logging.getLogger(__name__)


def build_app(config: Config) -> GatewayApp:
    """Oturum sağlığıyla birlikte gateway uygulamasını kur (test edilebilir)."""
    runtime = config.runtime
    health = HealthRegistry(
        failure_threshold=runtime.circuit_failure_threshold,
        cooldown_s=runtime.circuit_cooldown_s,
        alpha=runtime.reliability_alpha,
    )
    return GatewayApp(config, health=health)


def serve(config: Config, *, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Gateway'i çalıştır. `uvicorn` yoksa anlaşılır hata verir."""
    try:
        import uvicorn
    except ImportError as error:  # noqa: F841 — anlaşılır mesajla yeniden fırlatılır
        raise FusionError(
            "Gateway için 'uvicorn' gerekiyor ama kurulu değil. Kur: "
            "pip install 'fusion-cli[gateway]'"
        ) from None
    if host == "0.0.0.0":
        _logger.warning(
            "GÜVENLİK UYARISI: Fusion gateway 0.0.0.0 üzerinde tüm ağ arayüzlerine "
            "açılıyor. Yalnızca güvenilir bir ağda kullanın; Origin/CSRF koruması "
            "tarayıcı kaynaklı saldırıları sınırlar ancak kimlik doğrulaması sağlamaz."
        )
    uvicorn.run(build_app(config), host=host, port=port, log_level="warning")

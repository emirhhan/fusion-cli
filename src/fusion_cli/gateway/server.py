"""Yerel gateway sunucusunu çalıştır — `fusion serve`.

`uvicorn` yalnızca gateway kullanılınca gerekir (`fusion-cli[gateway]` ekstrası).
Kurulu değilse anlaşılır bir hata verilir; ürünün geri kalanı etkilenmez.
Sunucu varsayılan olarak yalnız yerelde dinler (127.0.0.1); ağa açmak belirteç ister.
"""

from __future__ import annotations

import logging

from ..config.models import Config
from ..core.errors import FusionError
from ..providers.health_setup import build_health
from ..ui import messages
from .access import is_loopback_address
from .app import GatewayApp

#: Varsayılan yerel adres ve port. Koda gömülü sihirli değer değil, gateway sabiti.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787

_logger = logging.getLogger(__name__)


def build_app(
    config: Config, *, compact_context: bool = False, access_token: str | None = None
) -> GatewayApp:
    """Oturum sağlığıyla birlikte gateway uygulamasını kur (test edilebilir)."""
    return GatewayApp(
        config,
        health=build_health(config),
        compact_context=compact_context,
        access_token=access_token,
    )


def serve(
    config: Config,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    compact_context: bool = False,
    access_token: str | None = None,
) -> None:
    """Gateway'i çalıştır. `uvicorn` yoksa anlaşılır hata verir.

    Yerel olmayan adrese (`0.0.0.0`, LAN IP) bağlanmak belirteç ister; belirteçsiz
    ağ bind'i başlatılmaz.
    """
    if not is_loopback_address(host) and not access_token:
        raise FusionError(messages.GATEWAY_NETWORK_BIND_NEEDS_TOKEN.format(host=host))
    try:
        import uvicorn
    except ImportError:
        raise FusionError(
            "Gateway için 'uvicorn' gerekiyor ama kurulu değil. Kur: "
            "pip install 'fusion-cli[gateway]'"
        ) from None
    if not is_loopback_address(host):
        _logger.warning(
            "GÜVENLİK UYARISI: Fusion gateway %s üzerinde ağa açılıyor. Bu bilgisayar "
            "dışından gelen istekler yalnız belirteçle kabul edilir; yalnız güvenilir "
            "bir ağda kullanın.",
            host,
        )
    uvicorn.run(
        build_app(config, compact_context=compact_context, access_token=access_token),
        host=host,
        port=port,
        log_level="warning",
    )

"""Oturum dayanıklılık kaydının TEK kurulum yeri.

REPL, masaüstü appserver'ı ve gateway aynı kaydı kurar; eskiden üç ayrı kopya
vardı ve masaüstü turu kaydı ajana hiç geçirmiyordu — circuit breaker yalnız
REPL'de yaşıyordu. Kayıt süreçler arası hız defterini de taşır.
"""

from __future__ import annotations

from ..config.models import Config
from ..core.health import HealthRegistry
from .rate_ledger import shared_rate_control


def build_health(config: Config, *, shared: bool = True) -> HealthRegistry:
    """Yapılandırma eşikleriyle sağlık kaydı; `shared` ise ortak hız defteriyle."""
    runtime = config.runtime
    return HealthRegistry(
        failure_threshold=runtime.circuit_failure_threshold,
        cooldown_s=runtime.circuit_cooldown_s,
        alpha=runtime.reliability_alpha,
        rate_control=shared_rate_control(runtime) if shared else None,
    )

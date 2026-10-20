"""Kök görevi tek döngüye ya da plan motoruna yönlendir.

Karar görev METNİNE bakmaz. Ölçüldü: kelime sınıflandırıcısıyla verilen rota,
oturumun ilk mesajının türünü sonraki "Tamam yaz" mesajına miras bıraktı ve iki
kelimelik bir onay plan motoruna girdi. Plan motoru artık yalnız açık bir seçimle
çalışır: yapılandırmada `workflow_mode: always` ya da kullanıcının `/plan-yurut`
makrosu. Çok adımlı işte planı model `todo_write` ile kendisi tutar.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ...core.execution_mode import ExecutionMode


class ExecutionRoute(Enum):
    """Bir kök görevin yürütme yolu."""

    FAST = "fast"
    WORKFLOW = "workflow"


@dataclass(frozen=True, slots=True)
class ExecutionRouteDecision:
    """Seçilen rota ve kullanıcıya açıklanabilir gerekçe."""

    route: ExecutionRoute
    reasons: tuple[str, ...]


def choose_execution_route(mode: ExecutionMode, *, requested: bool) -> ExecutionRouteDecision:
    """Yapılandırma ve kullanıcı seçiminden rotayı belirle.

    `requested`, kullanıcının bu tur için plan yürütmeyi açıkça seçtiğini söyler
    (`/plan-yurut`).
    """
    if requested:
        return ExecutionRouteDecision(ExecutionRoute.WORKFLOW, ("kullanıcı plan yürütmeyi seçti",))
    if mode is ExecutionMode.ALWAYS:
        return ExecutionRouteDecision(ExecutionRoute.WORKFLOW, ("workflow_mode=always",))
    return ExecutionRouteDecision(ExecutionRoute.FAST, ("tek ajan döngüsü",))

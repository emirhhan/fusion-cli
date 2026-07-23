"""Onay politikaları — "bu değişikliğe izin var mı?" sorusunun tek cevap yeri.

Üç mod tek bir protokolün arkasındadır; motor hangi modda olduğunu bilmez, yalnızca
`decide` çağırır. Yeni bir mod eklemek yeni bir sınıf yazmaktır.

    auto      değiştirici işlemlere otomatik evet — AMA yıkıcı komutta yine sorar
    plan      hiçbir değişikliğe izin yok; yalnızca keşif ve plan
    security  her değiştirici işlem tek tek sorulur

`auto` modunun yıkıcı komutlarda bile sorması bilinçlidir: otomatik onay hız içindir,
geri alınamaz bir işlemi sessizce yapmak için değil.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from ...core.tools import Tool, ToolArgs
from ...tools.safety import danger_reason


class ApprovalMode(Enum):
    """Kullanıcının seçtiği onay politikası."""

    AUTO = "auto"
    PLAN = "plan"
    SECURITY = "security"


class Decision(Enum):
    """Bir araç çağrısının akıbeti.

    `DENIED` ile `BLOCKED` ayrı tutulur: ilkinde kullanıcıya soruldu ve hayır dedi,
    ikincisinde politika gereği hiç sorulmadı. Model bu ikisine farklı tepki vermeli.
    """

    ALLOW = "allow"
    DENIED = "denied"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Onaya sunulan araç çağrısı."""

    tool: Tool
    args: ToolArgs
    #: Yıkıcı olduğu tespit edildiyse gerekçesi, değilse None.
    danger: str | None


class Prompter(Protocol):
    """Kullanıcıya evet/hayır sorabilen taraf. Motor terminali böyle görmez."""

    async def confirm(self, request: ApprovalRequest) -> bool: ...


class ApprovalPolicy(Protocol):
    """Bir araç çağrısına izin verilip verilmeyeceğine karar verir."""

    async def decide(self, request: ApprovalRequest) -> Decision: ...


class AutoApproval:
    """Değiştirici işlemlere otomatik evet; yıkıcı komutlarda yine de sorar."""

    def __init__(self, prompter: Prompter) -> None:
        self._prompter = prompter

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.danger is None:
            return Decision.ALLOW
        return _from_answer(await self._prompter.confirm(request))


class SecurityApproval:
    """Her değiştirici işlemi tek tek sorar."""

    def __init__(self, prompter: Prompter) -> None:
        self._prompter = prompter

    async def decide(self, request: ApprovalRequest) -> Decision:
        return _from_answer(await self._prompter.confirm(request))


class PlanApproval:
    """Plan modu: hiçbir değişikliğe izin verilmez, kullanıcıya da sorulmaz."""

    async def decide(self, request: ApprovalRequest) -> Decision:
        return Decision.BLOCKED


def build_policy(mode: ApprovalMode, prompter: Prompter) -> ApprovalPolicy:
    """Moda karşılık gelen politikayı üret."""
    if mode is ApprovalMode.PLAN:
        return PlanApproval()
    if mode is ApprovalMode.SECURITY:
        return SecurityApproval(prompter)
    return AutoApproval(prompter)


def build_request(tool: Tool, args: ToolArgs) -> ApprovalRequest:
    """Onay isteğini kur; yıkıcılık tespiti burada tek kez yapılır."""
    return ApprovalRequest(tool=tool, args=args, danger=danger_reason(tool.name, args))


def _from_answer(approved: bool) -> Decision:
    return Decision.ALLOW if approved else Decision.DENIED

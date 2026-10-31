"""Araç yasak listesi — `fusion agent --disallowed-tools` (Claude Code `--disallowedTools`).

İzin listesi (`--allowed-tools`) modele yalnız seçili araçları SUNAR (`run_agent(allowed_tools)`).
Yasak listesi ise tersidir: her şey sunulur, adı geçen araç çağrıldığında politika onu
SORMADAN engeller. İzin kurallarıyla aynı kalıptır — kullanıcıya hiç sorulmadığı için
karar `BLOCKED`tır, `DENIED` değil: model "bu yol kapalı, başka dene" bilgisini alır ve tur
durmaz (bkz. `approval.Decision`).

Ölçüldü (31 Ekim): yasaklı aracı kayıt defterinden düşürmek kayıt defteri `run_agent` içinde
kurulduğu için oturum katmanından yapılamıyordu; politika sarmalayıcısı aynı sonucu araç
yüzeyine dokunmadan verir.
"""

from __future__ import annotations

from collections.abc import Collection

from ...core.tools import ToolFamily, tool_family
from .approval import ApprovalPolicy, ApprovalRequest, Decision


class DeniedToolsPolicy:
    """Yasaklı aracı sormadan engelleyen, kalanını iç politikaya bırakan sarmalayıcı."""

    def __init__(self, inner: ApprovalPolicy, denied: Collection[str]) -> None:
        self._inner = inner
        self._denied = frozenset(name.strip() for name in denied if name.strip())

    @property
    def denied(self) -> frozenset[str]:
        return self._denied

    async def decide(self, request: ApprovalRequest) -> Decision:
        if self.is_denied(request.tool.name):
            return Decision.BLOCKED
        return await self._inner.decide(request)

    def is_denied(self, tool_name: str) -> bool:
        """Araç adı yasak listesinde mi? Kabuk takma adları (`run_shell` ↔ `bash`) tek ailedir."""
        if tool_name in self._denied:
            return True
        if tool_family(tool_name) is not ToolFamily.SHELL:
            return False
        return any(tool_family(name) is ToolFamily.SHELL for name in self._denied)

"""Araç yasak listesi — `fusion agent --disallowed-tools` (Claude Code `--disallowedTools`).

İzin listesi (`--allowed-tools`) modele yalnız seçili araçları SUNAR (`run_agent(allowed_tools)`).
Yasak listesi ise tersidir: her şey sunulur, adı geçen araç çağrıldığında politika onu
SORMADAN engeller. İzin kurallarıyla aynı kalıptır — kullanıcıya hiç sorulmadığı için
karar `BLOCKED`tır, `DENIED` değil: model "bu yol kapalı, başka dene" bilgisini alır ve tur
durmaz (bkz. `approval.Decision`).

Ölçüldü (31 Ekim): yasaklı aracı kayıt defterinden düşürmek kayıt defteri `run_agent` içinde
kurulduğu için oturum katmanından yapılamıyordu; politika sarmalayıcısı aynı sonucu araç
yüzeyine dokunmadan verir.

Ölçüldü (31 Ekim, 2. tur): politika yalnız DEĞİŞTİRİCİ araçta çağrılıyor (`loop._execute`);
`--disallowed-tools read_file,web_search` verilse de salt-okunur araç sunulup çalışıyordu.
Bu yüzden yasak listesi `AgentDeps.denied_tools` ile motora da gider: `_permitted` yasaklı
aracın şemasını hiç sunmaz, `_execute` çağrılırsa `BLOCKED` döner (ikinci savunma hattı).
`is_denied_tool` iki yerin ortak kuralıdır.
"""

from __future__ import annotations

from collections.abc import Collection

from ...core.tools import ToolFamily, tool_family
from .approval import ApprovalPolicy, ApprovalRequest, Decision, Denial


class DeniedToolsPolicy:
    """Yasaklı aracı sormadan engelleyen, kalanını iç politikaya bırakan sarmalayıcı."""

    def __init__(self, inner: ApprovalPolicy, denied: Collection[str]) -> None:
        self._inner = inner
        self._denied = frozenset(name.strip() for name in denied if name.strip())

    @property
    def denied(self) -> frozenset[str]:
        return self._denied

    async def decide(self, request: ApprovalRequest) -> Decision | Denial:
        if self.is_denied(request.tool.name):
            return Decision.BLOCKED
        return await self._inner.decide(request)

    def is_denied(self, tool_name: str) -> bool:
        """Araç adı yasak listesinde mi? Kabuk takma adları (`run_shell` ↔ `bash`) tek ailedir."""
        return is_denied_tool(tool_name, self._denied)


def is_denied_tool(tool_name: str, denied: Collection[str]) -> bool:
    """`tool_name` yasak listesine düşüyor mu? Kabuk ailesi (`run_shell`/`bash`) tek sayılır."""
    if not denied:
        return False
    if tool_name in denied:
        return True
    if tool_family(tool_name) is not ToolFamily.SHELL:
        return False
    return any(tool_family(name) is ToolFamily.SHELL for name in denied)

"""Ekip (P-061) ve iş akışı (P-062) koşularının ortak altyapısı.

İkisi de alt ajanı mevcut `team.run_subagent` ile başlatır (kişilik, araç süzgeci,
yazma alanı, çalışma ağacı, kart olayları aynen geçerli); burada yalnız üç ek parça var:

- `BudgetedRuns`: oturumun `ChildRuns` sahibine devreden (masaüstündeki "durdur" ve tur
  iptali bu ajanları da kapatır) ama KENDİ sayacını tutan koşu sahibi. Koşunun ajan
  bütçesi turun `max_subagents_per_turn` tavanından ayrıdır.
- `orchestration_deps`: üst `AgentDeps`'in sığ kopyası; bütçe, araç defteri ve tavan
  yalnız bu koşu için değişir, paylaşılan nesneler (yayıncı, bağlam, bütçe) aynen kalır.
- `ScopeGate`: eşzamanlı ajanların yazma alanı kapısı. `schedule_waves` kuralının canlı
  karşılığı: salt okuyan herkesle koşar, alanı bildiren yazar çakışmayanlarla koşar, alanı
  belirsiz yazar tek başına koşar.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.tools import Tool
from ...tools.registry import ToolRegistry
from .child_runs import ChildRuns
from .team_scope import paths_overlap

if TYPE_CHECKING:
    from .loop import AgentDeps, AgentOutcome


class BudgetedRuns(ChildRuns):
    """Üst sahibe devreden, kendi sayacı olan alt ajan sahibi."""

    def __init__(self, parent: ChildRuns) -> None:
        super().__init__()
        self._parent = parent
        self._own: set[str] = set()

    def start(
        self,
        identifier: str,
        work: Callable[[], Coroutine[object, object, AgentOutcome]],
    ) -> asyncio.Task[AgentOutcome]:
        task = self._parent.start(identifier, work)
        self._own.add(identifier)
        self.started_total += 1
        return task

    def detach(self, identifier: str, task: asyncio.Task[AgentOutcome]) -> None:
        self._own.discard(identifier)
        self._parent.detach(identifier, task)

    async def cancel(self, identifier: str) -> bool:
        return await self._parent.cancel(identifier)

    async def close(self) -> None:
        for identifier in tuple(self._own):
            await self._parent.cancel(identifier)
        self._own.clear()


def orchestration_deps(
    deps: AgentDeps,
    runs: BudgetedRuns,
    *,
    agent_limit: int,
    registry: ToolRegistry | None = None,
) -> AgentDeps:
    """Bu koşuya özgü bütçe/defterle üst bağımlılıkların sığ kopyası.

    `max_subagents_per_turn` koşunun ajan tavanına çekilir: `run_subagent` bütçe
    denetimini `deps.child_runs.started_total` ile yaptığı için sayaç ve tavan birlikte
    koşuya ait olur; torunlar da aynı kopyadan türediği için toplam bütçeye girer.
    """
    member = copy.copy(deps)
    runtime = dataclasses.replace(deps.config.runtime, max_subagents_per_turn=max(1, agent_limit))
    member.config = dataclasses.replace(deps.config, runtime=runtime)
    member.child_runs = runs
    if registry is not None:
        member.base_registry = registry
    return member


def registry_with(base: ToolRegistry, tools: tuple[Tool, ...]) -> ToolRegistry:
    """Temel defterin kopyası + koşuya özgü araçlar (paylaşılan defter kirlenmez)."""
    extended = ToolRegistry()
    for tool in base:
        if base.is_remote(tool.name):
            extended.register_or_replace(tool)
        else:
            extended.register(tool)
    for tool in tools:
        # `register`: koşu araçları uzak (MCP) sayılmasın; sıkı yüzey tavanına girmez.
        if extended.get(tool.name) is None:
            extended.register(tool)
    return extended


@dataclasses.dataclass(frozen=True, slots=True)
class _Hold:
    #: None = alanı belirsiz yazar (tek başına koşar); () = salt okur.
    scope: tuple[Path, ...] | None


class ScopeGate:
    """Yazma alanı çakışan ajanları sıraya sokan kapı."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._holds: list[_Hold] = []

    @asynccontextmanager
    async def hold(self, scope: tuple[Path, ...] | None) -> AsyncIterator[None]:
        entry = _Hold(scope)
        async with self._condition:
            await self._condition.wait_for(lambda: self._fits(entry))
            self._holds.append(entry)
        try:
            yield
        finally:
            async with self._condition:
                self._holds.remove(entry)
                self._condition.notify_all()

    def _fits(self, entry: _Hold) -> bool:
        if any(hold.scope is None for hold in self._holds):
            return False
        if entry.scope is None:
            return not self._holds
        return not any(
            paths_overlap(path, taken)
            for hold in self._holds
            if hold.scope
            for taken in hold.scope
            for path in entry.scope
        )


def gate_scope(read_only: bool, write_scope: tuple[Path, ...] | None) -> tuple[Path, ...] | None:
    """Kapı anahtarı: salt okur `()`, alanı bilinen yazar alanı, belirsiz yazar `None`."""
    if read_only:
        return ()
    return write_scope or None

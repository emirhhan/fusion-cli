"""Ekip ve iş akışı araçlarının tek kayıt noktası (paylaşılan dosyalarda tek satır kalsın).

- `register_orchestration_tools`: `build_agent_registry` çağırır; araçlar yalnız ana
  ajana (derinlik 0) sunulur — iç içe ekip/iş akışı yok (Claude Code ile aynı sınır).
- `ORCHESTRATION_SCOPED_TOOLS` + `orchestration_task_kinds`: şemalar yalnız isteğin
  gerçekten ekip/iş akışı istediği turda modele gider (istem bütçesi; bkz. `SCOPED_TOOLS`).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ...tools.registry import ToolRegistry
from .team import RunAgent
from .workflow_tools import workflow_run_tool

if TYPE_CHECKING:
    from .loop import AgentDeps

WORKFLOW_KIND = "is_akisi"

ORCHESTRATION_SCOPED_TOOLS: dict[str, str] = {
    "workflow_run": WORKFLOW_KIND,
}
ORCHESTRATION_KINDS = frozenset(ORCHESTRATION_SCOPED_TOOLS.values())

_WORKFLOW_TASK = re.compile(
    r"i[sş] ak[ıi][sş]|workflow|ultracode|orkestra|boru hatt|pipeline|fan-?out|"
    r"(çok|çoklu|paralel|birden çok|onlarca|yüzlerce) (alt )?ajan"
)


def orchestration_task_kinds(task: str) -> set[str]:
    """İsteğin açtığı görev türleri (ilgili araç şemaları yalnız o turda sunulur)."""
    # `re.IGNORECASE` Türkçe "İ"yi "i" saymaz; önce elle indirgenir.
    text = task.replace("İ", "i").lower()
    kinds: set[str] = set()
    if _WORKFLOW_TASK.search(text):
        kinds.add(WORKFLOW_KIND)
    return kinds


def register_orchestration_tools(
    registry: ToolRegistry, deps: AgentDeps, *, depth: int, run_agent: RunAgent
) -> None:
    if depth != 0:
        return
    registry.register(workflow_run_tool(deps, depth=depth, run_agent=run_agent))

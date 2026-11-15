"""Ekip ve iş akışı araçlarının tek kayıt noktası (paylaşılan dosyalarda tek satır kalsın).

- `register_orchestration_tools`: `build_agent_registry` çağırır; araçlar yalnız ana
  ajana (derinlik 0) sunulur — iç içe ekip/iş akışı yok (Claude Code ile aynı sınır).
  Ekip üyelerinin pano araçları (`team_tools_member`) yalnız üyenin defterine girer.
- `ORCHESTRATION_SCOPED_TOOLS` + `orchestration_task_kinds`: şemalar yalnız isteğin
  gerçekten ekip/iş akışı istediği turda modele gider (istem bütçesi; bkz. `SCOPED_TOOLS`).
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ...tools.registry import ToolRegistry
from .team import RunAgent
from .team_board import TeamStore
from .team_tools import team_run_tool
from .workflow_tools import workflow_run_tool, workflow_store

if TYPE_CHECKING:
    from .loop import AgentDeps

WORKFLOW_KIND = "is_akisi"
TEAM_KIND = "ekip"

ORCHESTRATION_SCOPED_TOOLS: dict[str, str] = {
    "workflow_run": WORKFLOW_KIND,
    "team_run": TEAM_KIND,
}
ORCHESTRATION_KINDS = frozenset(ORCHESTRATION_SCOPED_TOOLS.values())

# Kökler ek-dostu yazılır: Türkçede "ekip" ünlüyle başlayan ekte "ekib-" olur (ekibi,
# ekibe, ekibin), "takım" ekle uzar (takımı, takımla). Ölçüldü (31 Ekim): eski
# `\btak[ıi]m\b` "takımı"yı, `\bekip` "ekibi/ekibe"yi kaçırıyor, "ekipman"ı ise
# (motosiklet ekipmanı) yanlışlıkla ekip isteği sayıyordu.
_WORKFLOW_TASK = re.compile(
    r"i[sş] ak[ıi][sş]|workflow|ultracode|orkestra|boru hatt|pipeline|fan[- ]?out|"
    r"(çok|çoklu|paralel|birden çok|onlarca|yüzlerce) (alt )?ajan|alt ajanlar|sub-?agents?\b"
)

_TEAM_TASK = re.compile(r"\bekip(?!man)|\bekib|\btak[ıi]m(?!yıld)|\bteam|teammate|ekip arkada[sş]")

#: Kayıtlı ekip varken ekip aracını açık tutan devam istekleri ("devam et", "sürdür").
_CONTINUE = re.compile(r"\bdevam|\bs[üu]rd[üu]r|\bcontinue|\bresume|kald[ıi][gğ][ıi]n yerden")


def _mentions(text: str, names: list[str]) -> bool:
    return any(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) for name in names)


def _saved_kinds(text: str, root: Path) -> set[str]:
    """Kayıtlı ekip/iş akışı varken açılan türler (ad anılınca ya da devam turunda).

    Ölçüldü (31 Ekim): araç şeması yalnız "ekip" kelimesi geçen turda sunuluyordu;
    ertesi turda "devam et" denince `team_run` görünmez oluyordu.
    """
    kinds: set[str] = set()
    with contextlib.suppress(OSError):
        teams = TeamStore(root).names()
        if teams and (_CONTINUE.search(text) or _mentions(text, teams)):
            kinds.add(TEAM_KIND)
    with contextlib.suppress(OSError):
        saved = [item.name for item in workflow_store(root).definitions()]
        if saved and _mentions(text, saved):
            kinds.add(WORKFLOW_KIND)
    return kinds


def orchestration_task_kinds(task: str, root: Path | None = None) -> set[str]:
    """İsteğin açtığı görev türleri (ilgili araç şemaları yalnız o turda sunulur)."""
    # `re.IGNORECASE` Türkçe "İ"yi "i" saymaz; önce elle indirgenir.
    text = task.replace("İ", "i").lower()
    kinds: set[str] = set()
    if _WORKFLOW_TASK.search(text):
        kinds.add(WORKFLOW_KIND)
    if _TEAM_TASK.search(text):
        kinds.add(TEAM_KIND)
    if root is not None and kinds != ORCHESTRATION_KINDS:
        kinds |= _saved_kinds(text, root)
    return kinds


def register_orchestration_tools(
    registry: ToolRegistry, deps: AgentDeps, *, depth: int, run_agent: RunAgent
) -> None:
    if depth != 0:
        return
    registry.register(workflow_run_tool(deps, depth=depth, run_agent=run_agent))
    registry.register(team_run_tool(deps, depth=depth, run_agent=run_agent))

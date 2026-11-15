"""`task_stop`: arka plan işini kimliğiyle durdur (Claude Code TaskStop, #334).

Claude TaskStop `task_id` alır (eski `shell_id` kullanımdan kalktı; KillShell/KillBash
adları kural ve araç adı olarak çalışır). Fusion'da arka plan kabuk işleri ve `monitor`
izlemeleri aynı iş klasöründedir (`.fusion/is`); ikisi de buradan durur. Eski
`job_status(id, stop=true)` takma ad olarak çalışmaya devam eder (şemada yok).
"""

from __future__ import annotations

from ..core.tools import Tool, ToolArgs, ToolContext, ToolResult
from .jobs import _job_id, _stop

__all__ = ["TASK_STOP_TOOL", "task_stop"]


def _task_id(args: ToolArgs) -> str:
    for key in ("task_id", "shell_id", "id"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def task_stop(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Kabuk işini ya da `monitor` izlemesini durdur."""
    job_id = _task_id(args)
    if not job_id:
        return ToolResult.failure("'task_id' alanı gerekli (arka plan işinin kimliği).")
    from .ws_watch import stop_ws_watch

    if stop_ws_watch(job_id):
        return ToolResult(f"WebSocket izlemesi {job_id} durduruldu.")
    resolved = _job_id({"id": job_id}, context)
    if isinstance(resolved, ToolResult):
        return resolved
    return _stop(resolved[0], resolved[1], context)


TASK_STOP_TOOL = Tool(
    name="task_stop",
    description="Arka plan işini ya da monitor izlemesini kimliğiyle durdur.",
    parameters={
        "type": "object",
        "properties": {"task_id": {"type": "string"}},
        "required": ["task_id"],
    },
    run=task_stop,
    mutating=True,
)

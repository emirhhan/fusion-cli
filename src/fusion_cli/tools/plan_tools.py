"""`enter_plan_mode` / `exit_plan_mode` araçları (Claude Code: EnterPlanMode / ExitPlanMode).

`exit_plan_mode(plan)` planı onaya sunar: motor planı plan dosyasına yazar ve `PlanDrafted`
yayınlar; kabul kartı YALNIZ bu çağrıyla açılır (#317). `enter_plan_mode` modelin kendini
plan kipine geçirmesidir; izin gerekmez (#324).
"""

from __future__ import annotations

from ..core.tools import ToolArgs, ToolContext, ToolResult
from ..ui import messages

EXIT_PLAN_MODE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"plan": {"type": "string", "description": "Onaya sunulan plan (Markdown)"}},
    "required": ["plan"],
}

ENTER_PLAN_MODE_SCHEMA: dict[str, object] = {"type": "object", "properties": {}, "required": []}


async def exit_plan_mode_tool(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Planı kullanıcının onayına sun; plan kipinde değilken hata döner."""
    switch = context.plan_mode_switch
    if not (switch.active or switch.entered):
        return ToolResult.failure(messages.PLAN_TOOL_NOT_IN_PLAN_MODE)
    plan = args.get("plan")
    if not isinstance(plan, str) or not plan.strip():
        return ToolResult.failure(messages.PLAN_TOOL_EMPTY)
    switch.submit(plan.strip() + "\n")
    return ToolResult(messages.PLAN_TOOL_SUBMITTED)


async def enter_plan_mode_tool(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Plan kipine geç: bundan sonra dosya düzenlemeleri engellenir."""
    del args
    switch = context.plan_mode_switch
    if switch.in_plan_mode:
        return ToolResult(messages.PLAN_TOOL_ALREADY)
    switch.enter()
    return ToolResult(messages.PLAN_TOOL_ENTERED)

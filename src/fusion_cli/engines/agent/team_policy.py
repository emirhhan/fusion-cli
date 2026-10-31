"""Alt görevin etki gereksinimi parent güven sınırlarını genişletemez."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import TYPE_CHECKING

from ...tools.capabilities import expand_tool_patterns
from .edit_hooks import EDIT_TOOLS
from .execution_policy import ExecutionPolicy, policy_for
from .team_scope import derive_sub_context

if TYPE_CHECKING:
    from .loop import AgentDeps
    from .team import Persona, SubRun, SubTask


def child_execution(deps: AgentDeps, subtask: SubTask) -> ExecutionPolicy | None:
    parent = deps.execution
    if parent is None:
        return None
    child = policy_for(deps.config, deps.config.agent, subtask.task)
    return dataclasses.replace(
        parent,
        requires_tool_evidence=child.requires_tool_evidence,
        required_effect=child.required_effect,
        complex_task=child.complex_task,
        allow_mutation=parent.allow_mutation and child.allow_mutation and not subtask.read_only,
    )


def allowed_tools(
    deps: AgentDeps,
    persona: Persona,
    subtask: SubTask,
    *,
    available: tuple[str, ...] = (),
) -> set[str] | None:
    """Üyenin araç kümesi: `tools` ∖ `disallowedTools`, MCP sunucu süzgeci, yazma alanı.

    `available` çalışma-anı defterinin adlarıdır: `disallowedTools` ya da `mcpServers`
    kümeyi DARALTIR, bu yüzden tam yetkili (`None`) üye bile o anda adlandırılabilir bir
    kümeye iner. Her adım yalnız çıkarır; alt ajan üstünden fazla araç göremez.
    """
    allowed: set[str] | None = set(persona.tools) if persona.tools is not None else None
    if allowed is not None and available:
        allowed = expand_tool_patterns(allowed, available)
    if persona.disallowed_tools or persona.mcp_servers:
        if allowed is None:
            allowed = set(available) if available else None
        if allowed is not None:
            allowed = allowed - persona.disallowed_tools
            if persona.mcp_servers:
                allowed = {
                    name
                    for name in allowed
                    if not deps.base_registry.is_remote(name)
                    or name.split("__", 1)[0] in persona.mcp_servers
                }
    scope = derive_sub_context(deps.tool_context, subtask).write_scope
    if not subtask.read_only and scope is None:
        return allowed
    safe = {
        tool.name
        for tool in deps.base_registry
        if not tool.mutating or (not subtask.read_only and tool.name in EDIT_TOOLS)
    }
    return safe if allowed is None else allowed & safe


def member_brief(persona: Persona, subtask: SubTask, *, skills: str = "") -> str:
    """Üyenin talimatı + ön yüklenen beceriler + bu görevin sınırları (modelin göreceği not)."""
    parts = [persona.prompt.strip()] if persona.prompt.strip() else []
    if skills:
        parts.append(skills)
    if subtask.read_only:
        parts.append("Bu görevde SALT OKUYORSUN: dosya değiştirme, yalnız bulgularını raporla.")
    elif subtask.write_scope:
        alan = ", ".join(subtask.write_scope)
        parts.append(
            f"Yalnız şu yollara yazabilirsin: {alan}. Başka ajanlar aynı anda başka "
            "dosyalarda çalışıyor; alanın dışına çıkma."
        )
    return "\n\n".join(parts)


#: Bir üyenin ana bağlama dönen raporunun üst sınırı: `max_parallel_agents` uzun rapor
#: birleşince bağlam şişiyordu (A4-40).
MEMBER_REPORT_CHARS = 6_000


def cap_report(text: str, limit: int = MEMBER_REPORT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[… rapor kırpıldı; ayrıntı için değişen dosyalara bak.]"


def team_report(runs: Sequence[SubRun]) -> str:
    """Ana ajana dönen birleşik rapor: her üyenin sonucu kendi başlığıyla."""
    return "\n\n".join(
        f"## {run.persona.title} ({run.sub_id}) — {'tamam' if run.ok else 'yarım'}\n"
        f"{cap_report(run.text)}"
        for run in runs
    )


def summary(text: str, limit: int) -> str:
    first = " ".join(text.strip().split())
    return first if len(first) <= limit else first[: limit - 1] + "…"

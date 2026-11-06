"""Fresh current-authority context for a provider request, never persisted history."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from ...core.types import Message
from ...core.untrusted_text import neutralize_closing_tags
from ...tools.agent_catalog_index import agent_catalog_index
from ...tools.capabilities import Capability
from .agent_runtime_context import _sibling_description, launch_type_denial
from .context_budget import CHARS_PER_TOKEN_ESTIMATE
from .self_knowledge import session_line

if TYPE_CHECKING:
    from .loop import AgentDeps

_OPEN = "<fusion-current-capabilities>"
_CLOSE = "</fusion-current-capabilities>"
_INVOCATIONS = ("Agent", "Task", "invoke_agent", "spawn_agent", "spawn_agents", "invoke_subagent")


def request_capability_messages(
    messages: Sequence[Message],
    deps: AgentDeps,
    permitted: Collection[str],
    *,
    offer_tools: bool,
    depth: int,
    agents: tuple[Capability, ...],
) -> list[Message]:
    """Append one generated note to a copy, using permission before schema deferral."""
    from .team import depth_limit_reached

    names = set(permitted) if offer_tools else set()
    route = next((name for name in _INVOCATIONS if name in names), "")
    if depth_limit_reached(deps, depth) or deps.allowed_agent_types == ():
        route = ""
        names.difference_update(_INVOCATIONS)
    teacher = deps.config.teacher.model if deps.config.teacher is not None else ""
    parts = [
        "Bu not yalnız bu model isteğinin güncel yetkilerini gösterir; geçmişteki "
        "yetenek listeleri yeni izin vermez. Ertelenmiş ama izinli araçlar bu envanterde kalır.",
        session_line(names, teacher),
    ]
    if depth == 0 and route:
        parts.append(
            agent_catalog_index(
                None,
                agents=agents,
                include=lambda item, called: (
                    not launch_type_denial(
                        deps,
                        name=item.name,
                        source=item.source,
                        requested=called,
                    )
                ),
                invocation_tool=route,
                count_tokens=lambda text: (
                    (len(text) + CHARS_PER_TOKEN_ESTIMATE - 1) // CHARS_PER_TOKEN_ESTIMATE
                ),
            )
        )
    message_route = next((name for name in ("SendMessage", "send_message") if name in names), "")
    if message_route:
        parent = deps.runtime_parent_session or deps.conversation_id or deps.child_runs.session_id
        siblings = [
            state
            for state in deps.child_runs.records()
            if state.name
            and state.agent_id != deps.runtime_agent_id
            and state.root == str(deps.tool_context.root.resolve())
            and state.parent_session == parent
        ]
        if siblings:
            prefix = f"{message_route} ile ulaşılabilen ajanlar: " + ("main\n" if depth else "\n")
            parts.append(
                prefix
                + "\n".join(
                    _sibling_description(deps, state.name, state.agent_type, state.agent_id)
                    for state in siblings
                )
            )
    body = neutralize_closing_tags(
        "\n\n".join(part for part in parts if part), "fusion-current-capabilities"
    )
    block = _OPEN + "\n" + body + "\n" + _CLOSE
    view = list(messages)
    if view and view[0].role == "system":
        view[0] = replace(view[0], content=view[0].content + "\n\n" + block)
    else:
        view.insert(0, Message("system", block))
    return view

"""Agent aracında `subagent_type` çözümü Claude Code gibi (inceleme #4).

Tip verilmezse `general-purpose` kullanılır; o ajan bu oturumda yoksa (ör. ana ajanın
`tools: Agent(...)` listesi dışarıda bırakmış) `subagent_type is required` hatası döner.
Bilinmeyen tip sessizce genel yardımcıya düşmez; geçerli ajanları sayan hatayla reddedilir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...tools.capabilities import BUILTIN_AGENT_ALIASES

if TYPE_CHECKING:
    from .loop import AgentDeps

GENERAL_PURPOSE = "general-purpose"
FORK_TYPE = "fork"
_DISPLAY = {target: alias for alias, target in BUILTIN_AGENT_ALIASES.items()}

REQUIRED_MESSAGE = (
    "subagent_type is required: the general-purpose agent is not available in this session. "
    "Available agents: {agents}"
)
NOT_FOUND_MESSAGE = "Agent type '{name}' not found. Available agents: {agents}"


def _available(deps: AgentDeps) -> tuple[str, ...]:
    library = deps.capabilities
    if library is None:
        return ()
    names = tuple(
        dict.fromkeys(
            _DISPLAY.get(item.name, item.name) if item.source == "fusion" else item.name
            for item in library.agents()
        )
    )
    scope = getattr(deps, "allowed_agent_types", None)
    if scope is None:
        return names
    return tuple(name for name in names if name in scope or name.lower() in scope)


def _allowed(deps: AgentDeps, name: str) -> bool:
    scope = getattr(deps, "allowed_agent_types", None)
    return scope is None or name in scope


def resolve_agent_type(deps: AgentDeps, requested: str) -> tuple[str, str]:
    """`(çözülen tip, hata)`; hata boşsa tip kullanılır. Katalogsuz bağlam olduğu gibi geçer."""
    library = deps.capabilities
    name = requested.strip()
    if library is None or name == FORK_TYPE:
        return name, ""
    if not name:
        if library.get_agent(GENERAL_PURPOSE) is not None and _allowed(deps, GENERAL_PURPOSE):
            return GENERAL_PURPOSE, ""
        return "", REQUIRED_MESSAGE.format(agents=", ".join(_available(deps)) or "none")
    if library.get_agent(name) is None:
        return name, NOT_FOUND_MESSAGE.format(
            name=name, agents=", ".join(_available(deps)) or "none"
        )
    return name, ""

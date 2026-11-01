"""Claude Code `Agent would be spawned with zero tools` reddi (inceleme #5).

`tools` listesindeki her girdi üç gruptan birine düşerse ajan başlatılmaz: tanınmayan,
alt ajana verilmeyen (her alt ajandan alınanlar ya da arka plan süzgecinin attıkları) ve
bu oturumda hiçbir araçla eşleşmeyen. `tools` alanı yoksa, boşsa ya da `disallowedTools`
bütün girdileri kaldırdıysa ret yoktur (belge: errors.md).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...tools.capabilities import expand_tool_patterns, map_tools

if TYPE_CHECKING:
    from .loop import AgentDeps
    from .team import Persona

ZERO_TOOLS_MESSAGE = (
    "Agent '{name}' would be spawned with zero tools — refusing. Its tools list resolved to "
    "nothing: {groups}. Fix the agent's tools frontmatter or pass a different subagent_type."
)
_AGENT_NAMES = frozenset({"Agent", "Task", "spawn_agent", "spawn_agents", "invoke_subagent"})


def _background_kept() -> frozenset[str]:
    from .agent_runtime_context import _BACKGROUND_TOOLS
    from .team_settings import MEMORY_TOOL_NAMES

    return frozenset(map_tools(_BACKGROUND_TOOLS) or ()) | MEMORY_TOOL_NAMES


def _removed(deps: AgentDeps, depth: int) -> frozenset[str]:
    from .engine_tools import _subagent_removed_tools

    return _subagent_removed_tools(deps, depth + 1)


def _classify(
    deps: AgentDeps, persona: Persona, entry: str, *, depth: int, background: bool
) -> str:
    """Girdinin grubu: '' (çözülür), 'deny', 'unrecognized', 'unavailable', 'unmatched'."""
    mapped = map_tools((entry,))
    if mapped is None:
        return ""
    if not mapped:
        return "unrecognized"
    mapped -= persona.disallowed_tools
    if not mapped:
        return "deny"
    removed = _removed(deps, depth)
    if mapped <= _AGENT_NAMES and mapped & removed:
        return "unmatched"
    kept = mapped - removed
    if background:
        kept = {name for name in kept if name in _background_kept() or "__" in name}
    if not kept:
        return "unavailable"
    builtin = {name for name in kept if "__" not in name}
    registry = getattr(deps, "base_registry", None)
    if builtin or registry is None:
        return ""
    # Yalnız MCP girdisi: bağlı sunucuda karşılığı yoksa (`mcp__github__*`) eşleşmez.
    names = registry.names()
    return "" if expand_tool_patterns(kept, names) & set(names) else "unmatched"


_LABELS = (
    ("unrecognized", "unrecognized"),
    ("unavailable", "not available to subagents"),
    ("unmatched", "matched no tools in this session"),
)


def zero_tools_denial(deps: AgentDeps, persona: Persona, *, depth: int, background: bool) -> str:
    entries = persona.tool_entries
    if persona.tools is None or not entries:
        return ""
    groups: dict[str, list[str]] = {}
    for entry in entries:
        group = _classify(deps, persona, entry, depth=depth, background=background)
        if not group:
            return ""
        groups.setdefault(group, []).append(entry)
    if set(groups) == {"deny"}:
        return ""
    text = "; ".join(
        f"{label} [{', '.join(groups[key])}]" for key, label in _LABELS if key in groups
    )
    return ZERO_TOOLS_MESSAGE.format(name=persona.name, groups=text)

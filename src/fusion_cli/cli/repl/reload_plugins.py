"""REPL `/reload-plugins [--force]` — Claude Code karşılığı (#383).

Claude Code (https://code.claude.com/docs/en/plugins/cli-reference.md "/reload-plugins"):
bekleyen eklenti değişikliklerini (kur/güncelle/aç/kapat/diskte düzenleme) oturumu yeniden
başlatmadan uygular ve tek özet satırı basar: `Reloaded: N plugins · N skills · N agents ·
N hooks · N plugin MCP servers · N plugin LSP servers`. Yeniden yükleme bir eklenti MCP
sunucusunu ekleyip çıkaracaksa (istem önbelleği bozulur) `--force` olmadan uygulanmaz.
"""

from __future__ import annotations

from pathlib import Path

from ...config.claude_plugins import claude_plugin_layouts
from ...config.loader import refresh_plugin_mcp_servers
from ...config.models import Config, McpScope
from ...config.plugin_hooks import plugin_hooks
from ...config.plugin_store import active_plugins
from ...tools.plugin_capabilities import PLUGIN_SOURCE
from .state import ReplState

SUMMARY = (
    "Yeniden yüklendi: {plugins} eklenti · {skills} beceri · {agents} ajan · {hooks} kanca · "
    "{mcp} eklenti MCP sunucusu · 0 eklenti LSP sunucusu"
)
NEEDS_FORCE = (
    "Bu yeniden yükleme MCP araçlarını değiştiriyor ({servers}) — sonraki mesajın önbellek "
    "yerine bütün konuşmayı yeniden okur. Uygulamak için /reload-plugins --force çalıştır."
)
USAGE = "Kullanım: /reload-plugins [--force]"
_FORCE = frozenset({"--force", "force"})
_HOOK_TIMEOUT_S = 60.0


def _plugin_servers(config: Config) -> frozenset[str]:
    return frozenset(s.name for s in config.mcp_servers if s.scope is McpScope.PLUGIN)


def reload_plugins_command(state: ReplState, argument: str) -> str:
    words = argument.split()
    if any(word not in _FORCE for word in words):
        return USAGE
    refreshed = refresh_plugin_mcp_servers(state.config)
    changed = sorted(_plugin_servers(state.config) ^ _plugin_servers(refreshed))
    if changed and not words:
        return NEEDS_FORCE.format(servers=", ".join(changed))
    state.config = refreshed
    skills = agents = 0
    registry = state.capabilities
    home = Path.home()
    if registry is not None:
        registry.invalidate()
        skills = sum(1 for item in registry.skills() if PLUGIN_SOURCE in item.source.split("+"))
        agents = len(registry.agents())
        home = registry.home
    fusion = {item.record.name for item in active_plugins()}
    claude = {layout.name for _id, layout in claude_plugin_layouts(home)}
    plugins = len(fusion | claude)
    hooks = len(plugin_hooks(default_timeout_s=_HOOK_TIMEOUT_S)[0])
    return SUMMARY.format(
        plugins=plugins,
        skills=skills,
        agents=agents,
        hooks=hooks,
        mcp=len(_plugin_servers(refreshed)),
    )

"""stream-json `system/init` mesajı ve `initialize` cevabının keşif alanları (#280).

Agent SDK istemcisi komut listesini `system/init`'in `slash_commands` / `skills` / `plugins`
alanlarından ve `initialize` denetim cevabının `commands` dizisinden okur. Bunlar koşunun
beceri kataloğundan (`CapabilityRegistry`) ve `-p`'de çalışan yerleşik komutlardan kurulur.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .. import __version__
from ..engines.agent.approval import ApprovalMode
from ..tools.capabilities import CapabilityRegistry
from .print_builtins import BUILTINS
from .sdk_messages import CLAUDE_MODE_NAMES, claude_tool_name


@dataclass(frozen=True, slots=True)
class CatalogSummary:
    """Komut/beceri/eklenti keşif bilgisi."""

    slash_commands: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    plugins: tuple[dict[str, str], ...] = ()
    commands: tuple[dict[str, str], ...] = ()


def catalog_summary(
    registry: CapabilityRegistry | None, plugins: Sequence[tuple[str, str]] = ()
) -> CatalogSummary:
    """Kullanıcının `/ad` ile çağırabildiği beceri/komutlar + `-p` yerleşikleri."""
    items = [item for item in (registry.skills() if registry else ()) if item.user_invocable]
    commands = [
        {"name": item.name, "description": item.description, "argumentHint": item.argument_hint}
        for item in sorted(items, key=lambda item: item.name)
    ]
    commands += [
        {"name": name, "description": "", "argumentHint": ""}
        for name in sorted(BUILTINS)
        if name not in {item["name"] for item in commands}
    ]
    return CatalogSummary(
        slash_commands=tuple(item["name"] for item in commands),
        skills=tuple(sorted(item.name for item in items if item.kind == "beceri")),
        plugins=tuple({"name": name, "path": path} for name, path in plugins),
        commands=tuple(commands),
    )


def active_plugin_paths() -> tuple[tuple[str, str], ...]:
    """Etkin eklentilerin (ad, kök) çiftleri; okunamazsa boş."""
    from ..config.plugin_store import active_plugins

    try:
        found = active_plugins()
    except OSError:
        return ()
    return tuple(
        (item.record.name, str(item.layout.root)) for item in found if item.layout is not None
    )


def init_message(
    *,
    session_id: str,
    cwd: str,
    model: str,
    mode: ApprovalMode,
    mcp_servers: Sequence[str],
    mcp_errors: Sequence[Mapping[str, str]] = (),
    tools: Sequence[str] = (),
    agents: Sequence[str] = (),
    catalog: CatalogSummary | None = None,
) -> dict[str, object]:
    """`system/init` (stream-json'un ilk satırı)."""
    summary = catalog or CatalogSummary()
    message: dict[str, object] = {
        "type": "system",
        "subtype": "init",
        "cwd": cwd,
        "session_id": session_id,
        "tools": [claude_tool_name(name) for name in tools],
        "mcp_servers": [{"name": name, "status": "pending"} for name in mcp_servers],
        "model": model,
        "permissionMode": CLAUDE_MODE_NAMES.get(mode, mode.value),
        "slash_commands": list(summary.slash_commands),
        "apiKeySource": "none",
        "claude_code_version": __version__,
        "output_style": "default",
        "agents": list(agents),
        "skills": list(summary.skills),
        "plugins": [dict(item) for item in summary.plugins],
        "uuid": str(uuid.uuid4()),
    }
    if mcp_errors:
        message["mcp_server_errors"] = [dict(item) for item in mcp_errors]
    return message

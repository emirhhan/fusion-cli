"""`plugin list --json [--available]`, `plugin details` ve `plugin prune` (Claude Code birebir).

#380 (details, prune), #381 (--json), #415 (list --available). Ağ YOK: git pazarları kayıt
anındaki klondan okunur.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ..config.plugin_layout import PluginLayout, context_cost, validate_plugin
from ..config.plugin_scopes import SCOPE_PROJECT, scope_values
from ..config.plugin_store import (
    STATUS_BROKEN,
    STATUS_TAMPERED,
    InstalledPlugin,
    installed_plugins,
    load_state,
    plugin_id,
    plugins_dir,
)
from ..core.plugin_marketplace import MarketplaceSource
from ..core.plugins import PluginError
from .plugin_install import browse
from .plugin_toggle import find_record

#: Claude: bildirimde `version` yoksa `unknown`.
UNKNOWN_VERSION = "unknown"
ERR_DETAILS_MISSING = (
    'Eklenti "{name}" bulunamadı. Kurulu eklentileri görmek için `fusion plugin list` çalıştır.'
)
NOTHING_TO_PRUNE = "Nothing to prune: otomatik kurulmuş, artık gerekmeyen bağımlılık yok."
DRY_RUN_SUFFIX = "(dry run — nothing removed)"
SECTION_INVENTORY = "Component inventory"
SECTION_COST = "Projected token cost"
SECTION_PER_COMPONENT = "Per-component (rounded)"


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat().replace("+00:00", "Z")


def _project_enabled(item: InstalledPlugin, root: Path) -> bool | None:
    values = scope_values(SCOPE_PROJECT, root)
    for key in (plugin_id(item.record), item.record.name):
        if key in values:
            return values[key]
    return None


def _installed_entry(item: InstalledPlugin, base: Path, root: Path) -> dict[str, object]:
    record = item.record
    entry: dict[str, object] = {
        "id": plugin_id(record),
        "version": record.version or UNKNOWN_VERSION,
        "scope": "user",
        "enabled": record.enabled and item.status not in (STATUS_BROKEN, STATUS_TAMPERED),
        "installPath": str(base / record.name),
    }
    if record.installed_at:
        entry["installedAt"] = _iso(record.installed_at)
        entry["lastUpdated"] = _iso(record.installed_at)
    if item.status == STATUS_BROKEN:
        entry["errors"] = [item.detail or STATUS_BROKEN]
    elif item.status == STATUS_TAMPERED:
        entry["notes"] = [item.detail]
    if item.layout is not None:
        report = validate_plugin(item.layout.root, record.name)
        if report.servers:
            entry["mcpServers"] = {server.name: _server(server) for server in report.servers}
    project = _project_enabled(item, root)
    if record.marketplace and project is not None:
        entry["projectEnabled"] = project
    return entry


def _server(server: object) -> dict[str, object]:
    fields = ("command", "args", "url", "transport")
    return {name: value for name in fields if (value := getattr(server, name, None))}


def _source(source: MarketplaceSource) -> str | dict[str, str]:
    if source.kind == "path":
        # Ayrıştırıcı `./` önekini atar; Claude girdideki göreli yolu `./…` olarak gösterir.
        location = source.location.removeprefix("./").strip("/")
        return f"./{location}" if location not in ("", ".") else "./"
    payload = {"source": "url", "url": source.location}
    if source.ref:
        payload["ref"] = source.ref
    if source.sha:
        payload["sha"] = source.sha
    return payload


def _available(base: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in browse(base=base):
        if item.installed:
            continue
        entry: dict[str, object] = {
            "pluginId": f"{item.entry.name}@{item.marketplace}",
            "name": item.entry.name,
            "marketplaceName": item.marketplace,
            "source": _source(item.entry.source),
        }
        if item.entry.description:
            entry["description"] = item.entry.description
        if item.entry.version:
            entry["version"] = item.entry.version
        rows.append(entry)
    return rows


def list_payload(
    *, available: bool = False, base: Path | None = None, root: Path | None = None
) -> list[dict[str, object]] | dict[str, object]:
    """Claude `plugin list --json`: dizi; `--available` ile `{installed, available}` nesnesi."""
    store = base or plugins_dir()
    project = root or Path.cwd()
    installed = [_installed_entry(item, store, project) for item in installed_plugins(store, root)]
    if not available:
        return installed
    return {"installed": installed, "available": _available(store)}


def details_text(name: str, *, base: Path | None = None) -> str:
    """Claude `plugin details`: kimlik, bileşen envanteri, öngörülen token maliyeti."""
    store = base or plugins_dir()
    try:
        record = find_record(load_state(store), name)
    except PluginError as error:
        raise PluginError(ERR_DETAILS_MISSING.format(name=name)) from error
    report = validate_plugin(store / record.name, record.name)
    layout = report.layout
    if layout is None:
        raise PluginError(ERR_DETAILS_MISSING.format(name=name))
    manifest = layout.manifest
    rows = [
        f"{plugin_id(record)} {manifest.version or UNKNOWN_VERSION}",
        *([manifest.description] if manifest.description else []),
        f"Kaynak: {record.source or record.kind}",
        "",
        f"{SECTION_INVENTORY}:",
        f"  Skills: {len(layout.skills)}",
        f"  Commands: {len(layout.commands) + len(layout.inline_commands)}",
        f"  Agents: {len(layout.agents)}",
        f"  Hooks: {report.hook_count}",
        f"  MCP servers: {len(report.servers)}",
        "  LSP servers: 0",
        "",
        f"{SECTION_COST}: ~{context_cost(layout)} token (her oturumda sürekli)",
    ]
    rows.extend(_per_component(layout))
    return "\n".join(rows)


def _per_component(layout: PluginLayout) -> list[str]:
    paths = (*layout.skills, *layout.agents, *(path for _name, path in layout.commands))
    if not paths:
        return []
    rows = ["", f"{SECTION_PER_COMPONENT}:"]
    for path in paths:
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        label = path.parent.name if path.name == "SKILL.md" else path.stem
        rows.append(f"  {label}: çağrıldığında ~{round(size / 4, -1):.0f} token")
    return rows


def prune_text(*, dry_run: bool = False) -> str:
    """Fusion bağımlılıkları otomatik kurmaz (#389); budanacak eklenti hiçbir zaman yoktur."""
    return f"{NOTHING_TO_PRUNE} {DRY_RUN_SUFFIX}" if dry_run else NOTHING_TO_PRUNE

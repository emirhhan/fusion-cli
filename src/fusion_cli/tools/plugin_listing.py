"""`plugin list --json [--available]`, `plugin details` ve `plugin prune` (Claude Code birebir).

#380 (details, prune), #381 (--json), #415 (list --available). Ağ YOK: git pazarları kayıt
anındaki klondan okunur.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ..config.plugin_layout import PluginLayout, context_cost, validate_plugin
from ..config.plugin_scopes import SCOPE_PROJECT, scope_values
from ..config.plugin_session import SESSION_HEADING, SESSION_SCOPE, session_plugins
from ..config.plugin_store import (
    STATUS_BROKEN,
    STATUS_TAMPERED,
    InstalledPlugin,
    installed_plugins,
    load_state,
    plugin_folder,
    plugin_id,
    plugins_dir,
)
from ..core.plugin_marketplace import MarketplaceSource
from ..core.plugins import PluginError
from .plugin_install import browse
from .plugin_toggle import find_record

ERR_DATA_SIZE_MISSING = "--data-size kurulu olmayan bir eklentiyi gösteriyor"
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
        "installPath": str(plugin_folder(record, base)),
    }
    if record.folder:
        entry["readFromFolder"] = record.folder
        if item.layout is not None and item.layout.manifest.version:
            entry["folderVersion"] = item.layout.manifest.version
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


def _session_entry(item: InstalledPlugin) -> dict[str, object]:
    record = item.record
    return {
        "id": plugin_id(record),
        "version": record.version or UNKNOWN_VERSION,
        "scope": SESSION_SCOPE,
        "enabled": True,
        "installPath": record.source,
    }


def session_text() -> str:
    """İnsan okunur listenin `Session-only plugins` ve `Skills-directory plugins` bölümleri."""
    parts = [
        _section(SESSION_HEADING, session_plugins()),
        _skills_dir_section(),
    ]
    return "\n\n".join(p for p in parts if p)


def _section(
    heading: str, items: tuple[InstalledPlugin, ...], states: dict[str, str] | None = None
) -> str:
    if not items:
        return ""
    rows = [heading]
    for item in items:
        version = f" {item.record.version}" if item.record.version else ""
        state = (states or {}).get(item.record.name, "")
        rows.append(f"  {plugin_id(item.record)}{version} — {item.record.source}{state}")
    return "\n".join(rows)


def _skills_dir_section() -> str:
    from ..config.plugin_skills_dir import (
        SKILLS_DIR_HEADING,
        skills_dir_enabled,
        skills_dir_plugins,
    )

    items = skills_dir_plugins()
    root = Path.cwd()
    states = {i.record.name: "" if skills_dir_enabled(i, root) else " (kapalı)" for i in items}
    return _section(SKILLS_DIR_HEADING, items, states)


def _skills_dir_entries() -> list[dict[str, object]]:
    """Claude `list --json`: `{id: ad@skills-dir, version, scope: user, enabled, installPath}`."""
    from ..config.plugin_skills_dir import SKILLS_DIR_SCOPE, skills_dir_enabled, skills_dir_plugins

    root = Path.cwd()
    return [
        {
            "id": plugin_id(item.record),
            "version": item.record.version or UNKNOWN_VERSION,
            "scope": SKILLS_DIR_SCOPE,
            "enabled": skills_dir_enabled(item, root),
            "installPath": item.record.source,
        }
        for item in skills_dir_plugins()
    ]


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


def human_size(size: int) -> str:
    """Claude `dataDirSize.human` biçimi: 1024 tabanlı, tek ondalık (5000 → `4.9KB`)."""
    value, unit = float(size), "B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            break
        value /= 1024
    return f"{size}B" if unit == "B" else f"{value:.1f}{unit}"


def _data_size(record_name: str) -> dict[str, object] | None:
    from ..config.plugin_data import plugin_data_dir

    folder = plugin_data_dir(record_name)
    if not folder.is_dir():
        return None
    total = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file() and not p.is_symlink())
    return {"bytes": total, "human": human_size(total)}


def _with_sizes(
    rows: list[dict[str, object]], items: tuple[InstalledPlugin, ...], data_size: str
) -> list[dict[str, object]]:
    """`--data-size [eklenti]`: kurulu eklentinin veri klasörü varsa `dataDirSize` (#381)."""
    wanted = {plugin_id(item.record): item.record.name for item in items}
    if data_size:
        hits = [i for i, n in wanted.items() if data_size in (i, n)]
        if not hits:
            raise PluginError(ERR_DATA_SIZE_MISSING)
        wanted = {hits[0]: wanted[hits[0]]}
    sized: list[dict[str, object]] = []
    for row in rows:
        size = _data_size(wanted[str(row["id"])]) if row["id"] in wanted else None
        sized.append({**row, "dataDirSize": size} if size is not None else row)
    return sized


def list_payload(
    *,
    available: bool = False,
    base: Path | None = None,
    root: Path | None = None,
    data_size: str | None = None,
) -> list[dict[str, object]] | dict[str, object]:
    """Claude `plugin list --json`: dizi; `--available` ile `{installed, available}` nesnesi."""
    store = base or plugins_dir()
    project = root or Path.cwd()
    items = installed_plugins(store, root)
    installed = [_installed_entry(item, store, project) for item in items]
    if data_size is not None:
        installed = _with_sizes(installed, items, data_size)
    if base is None:
        installed.extend(_session_entry(item) for item in session_plugins())
        installed.extend(_skills_dir_entries())
    if not available:
        return installed
    return {"installed": installed, "available": _available(store)}


def details_text(name: str, *, base: Path | None = None) -> str:
    """Claude `plugin details`: kimlik, bileşen envanteri, öngörülen token maliyeti."""
    store = base or plugins_dir()
    bare, _, market = name.partition("@")
    from ..config.plugin_skills_dir import find_skills_dir

    skills_dir = find_skills_dir(name)
    session = [i.record for i in session_plugins() if i.record.name == bare]
    if skills_dir is not None and market in ("", skills_dir.record.marketplace) and not session:
        session = [skills_dir.record]
    if session and market in ("", session[0].marketplace):
        record = session[0]
        folder = Path(record.source)
    else:
        try:
            record = find_record(load_state(store), name)
        except PluginError as error:
            raise PluginError(ERR_DETAILS_MISSING.format(name=name)) from error
        folder = plugin_folder(record, store)
    report = validate_plugin(folder, record.name)
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

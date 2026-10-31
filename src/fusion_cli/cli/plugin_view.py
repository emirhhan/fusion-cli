"""Eklenti listesinin, önizlemenin ve doğrulama raporunun metni (P-059): CLI ve REPL ortak."""

from __future__ import annotations

from ..config.plugin_layout import PluginLayout, ValidationReport, server_target
from ..config.plugin_store import PLUGIN_HOOKS_ACTIVE, InstalledPlugin, PluginState
from ..tools.plugin_install import CatalogEntry, PluginPreview

EMPTY = (
    "Kurulu eklenti yok. Örnek: fusion eklenti kur ./eklentim · "
    "pazar: fusion eklenti pazar ekle resmi"
)
ALL_OFF = "Bütün eklentiler kapalı (fusion eklenti ac --hepsi ile açılır)."
EXEC_WARNING = (
    "DİKKAT: bu eklenti Fusion dışında komut çalıştırabilir ({parts}). Kancalar her olayda, MCP "
    "sunucuları oturum açılışında başlar; MCP araç çağrıları yine onay ister."
)
HOOKS_NOT_RUN = (
    "Not: Fusion bu sürümde eklenti kancalarını henüz ÇALIŞTIRMIYOR; kancalar onaylansa da "
    "tetiklenmez (kanca desteği ayrıca gelecek)."
)
DIGEST_HINT = (
    "  karma: {digest} (onaylamak için: fusion eklenti kur {source} --yes --karma {digest})"
)
NO_MARKETS = "Kayıtlı pazar yok. Örnek: fusion eklenti pazar ekle resmi"
NO_ENTRIES = "Pazarlarda eklenti bulunamadı."
VALID = "Geçerli: {name}"
INVALID = "Geçersiz:"


def components(
    layout: PluginLayout, *, hooks: int | None = None, servers: int | None = None
) -> str:
    """`3 beceri · 2 komut · 1 ajan · kancalar · 1 MCP` özeti."""
    parts = [
        f"{len(layout.skills)} beceri" if layout.skills else "",
        f"{len(layout.commands)} komut" if layout.commands else "",
        f"{len(layout.agents)} ajan" if layout.agents else "",
        f"{len(layout.output_styles)} çıktı stili" if layout.output_styles else "",
        (f"{hooks} kanca" if hooks is not None else "kancalar") if layout.has_hooks else "",
        (f"{servers} MCP sunucusu" if servers is not None else "MCP") if layout.has_mcp else "",
    ]
    return " · ".join(part for part in parts if part) or "bileşen yok"


def exec_parts(layout: PluginLayout) -> str:
    return ", ".join(
        p for p in ("kanca" if layout.has_hooks else "", "MCP" if layout.has_mcp else "") if p
    )


def format_installed(items: tuple[InstalledPlugin, ...], state: PluginState) -> str:
    if not items:
        return EMPTY
    rows = [ALL_OFF] if state.all_disabled else []
    for item in items:
        record = item.record
        version = f" {record.version}" if record.version else ""
        summary = components(item.layout) if item.layout else item.detail
        origin = record.marketplace or record.kind
        rows.append(f"  {record.name}{version} — {item.status} · {summary} · {origin}")
        if item.detail and item.layout is not None:
            rows.append(f"      {item.detail} (yeniden onay: fusion eklenti guven {record.name})")
    if not PLUGIN_HOOKS_ACTIVE and any(i.layout and i.layout.has_hooks for i in items):
        rows.append(HOOKS_NOT_RUN)
    return "\n".join(rows)


def format_preview(preview: PluginPreview) -> str:
    report = preview.report
    if report.layout is None:
        return format_validation(report)
    manifest = report.layout.manifest
    rows = [
        f"{manifest.name} {manifest.version}".strip()
        + (f" — {manifest.description}" if manifest.description else ""),
        "  bileşenler: "
        + components(report.layout, hooks=report.hook_count, servers=len(report.servers)),
        f"  bağlam maliyeti: ~{preview.context_tokens} token/tur",
    ]
    if manifest.author:
        rows.append(f"  yazar: {manifest.author}")
    rows.extend(f"  kanca: {line}" for line in report.hook_lines)
    rows.extend(
        f"  MCP: {server.name} → {server_target(server, report.layout.root)}"
        for server in report.servers
    )
    rows.extend(f"  ! {warning}" for warning in report.warnings)
    rows.extend(f"  ✗ {error}" for error in report.errors)
    if report.layout.is_executable:
        rows.append(EXEC_WARNING.format(parts=exec_parts(report.layout)))
    if report.layout.has_hooks and not PLUGIN_HOOKS_ACTIVE:
        rows.append(HOOKS_NOT_RUN)
    return "\n".join(rows)


def format_validation(report: ValidationReport) -> str:
    if report.ok and report.layout is not None:
        head = VALID.format(name=report.layout.name)
        body = components(report.layout, hooks=report.hook_count, servers=len(report.servers))
        lines = [f"{head} · {body}", *(f"  ! {w}" for w in report.warnings)]
        return "\n".join(lines)
    return "\n".join(
        [INVALID, *(f"  ✗ {e}" for e in report.errors), *(f"  ! {w}" for w in report.warnings)]
    )


def format_catalog(entries: tuple[CatalogEntry, ...]) -> str:
    if not entries:
        return NO_ENTRIES
    rows = []
    for item in entries:
        mark = "✓" if item.installed else " "
        version = f" {item.entry.version}" if item.entry.version else ""
        description = f" — {item.entry.description}" if item.entry.description else ""
        rows.append(f"  {mark} {item.entry.name}@{item.marketplace}{version}{description}")
    return "\n".join(rows)


def format_marketplaces(state: PluginState) -> str:
    if not state.marketplaces:
        return NO_MARKETS
    return "\n".join(f"  {m.name} — {m.kind} · {m.source}" for m in state.marketplaces)

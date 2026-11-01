"""Masaüstü RPC'leri: eklentiler (P-059), içe aktarma ve sürüm notları (P-071).

    eklenti.listele | eklenti.onizle {kaynak} | eklenti.kur {kaynak, onay, beklenen_karma}
    eklenti.etkinlik {ad|hepsi, etkin} | eklenti.kaldir {ad}
    eklenti.guven {ad} → önizleme · {ad, onay, beklenen_karma} → onay
    eklenti.guncelle {ad, onay?, beklenen_karma?} | eklenti.dogrula {ad}
    eklenti.pazar_guncelle {ad}
    eklenti.kesfet {pazar?} | eklenti.pazar_ekle {kaynak} | eklenti.pazar_kaldir {ad}
    ice_aktar.onizle {kaynak} | ice_aktar.uygula {kaynak}
    surum.notlari {surum?}

CLI ve REPL ile aynı işlevleri çağırır. Kanca/MCP içeren eklenti `onay: true` olmadan
kurulmaz; yanıt `onay_gerekli` ve önizlemeyi taşır, arayüz kullanıcıya gösterip yeniden ister.
Önizleme içeriğin karmasını (`karma`) taşır; onaylı istek bunu `beklenen_karma` olarak geri
yollar ve araya giren değişiklik (pinsiz git HEAD'i, yerel klasör) kurulmaz. `eklenti.guven`
onaysız çağrıda yalnız güncel içeriğin önizlemesini döner.
Yanıtta `yenile: true` varsa oturum beceri kataloğunu yeniden tarar. Sır değeri hiçbir yanıtta
yer almaz.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import __version__
from ..config.importers import ImportPlan, apply_plan, build_plan, default_secrets
from ..config.loader import refresh_plugin_mcp_servers
from ..config.models import Config, McpScope
from ..config.plugin_layout import PluginLayout, server_target, validate_plugin
from ..config.plugin_store import (
    PLUGIN_HOOKS_ACTIVE,
    InstalledPlugin,
    inspect_plugin,
    installed_plugins,
    load_state,
    plugin_folder,
)
from ..config.release_notes import changelog_path, load_sections, release_notes_text
from ..core.errors import ConfigError
from ..core.plugins import PluginError
from ..tools import plugin_install as plugins
from ..tools import plugin_update

EXTENSION_ROUTES = frozenset(
    {
        "eklenti.listele",
        "eklenti.onizle",
        "eklenti.kur",
        "eklenti.etkinlik",
        "eklenti.kaldir",
        "eklenti.guven",
        "eklenti.guncelle",
        "eklenti.dogrula",
        "eklenti.kesfet",
        "eklenti.pazar_ekle",
        "eklenti.pazar_kaldir",
        "eklenti.pazar_guncelle",
        "ice_aktar.onizle",
        "ice_aktar.uygula",
        "surum.notlari",
    }
)

NEEDS_SOURCE = "Kaynak ver: klasör, https git adresi, sahip/repo ya da ad@pazar."
NEEDS_NAME = "Eklenti adı ver."
NEEDS_APPROVAL = "Bu eklenti komut çalıştırabilir (kanca/MCP); incele ve onayla."
NEEDS_REAPPROVAL = "Eklentinin dosyaları değişti; güncel içeriği incele ve onayla."


@dataclass(frozen=True, slots=True)
class ExtensionContext:
    root: Path
    home: Path
    config: Config


@dataclass(frozen=True, slots=True)
class ExtensionResult:
    payload: dict[str, Any]
    #: İçe aktarma ya da eklenti değişikliği MCP kayıtlarını değiştirdiyse yeni yapılandırma.
    config: Config | None = None
    #: Oturumdan çıkan eklenti MCP sunucuları: canlı bağlantıları hemen kapatılır.
    dropped: tuple[str, ...] = ()


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def _components(layout: PluginLayout) -> dict[str, Any]:
    return {
        "beceri": len(layout.skills),
        "komut": len(layout.commands),
        "ajan": len(layout.agents),
        "stil": len(layout.output_styles),
        "kanca": layout.has_hooks,
        "mcp": layout.has_mcp,
    }


def _installed(item: InstalledPlugin) -> dict[str, Any]:
    record, layout = item.record, item.layout
    return {
        "ad": record.name,
        "surum": record.version,
        "aciklama": layout.manifest.description if layout else "",
        "durum": item.status,
        "ayrinti": item.detail,
        "kaynak": record.source,
        "tur": record.kind,
        "pazar": record.marketplace,
        "commit": record.commit[:12],
        "etkin": record.enabled,
        "calistirilabilir": bool(layout and layout.is_executable),
        "bilesenler": _components(layout) if layout else {},
    }


def _preview(preview: plugins.PluginPreview) -> dict[str, Any]:
    report = preview.report
    layout = report.layout
    root = layout.root if layout else Path()
    return {
        "ad": layout.name if layout else "",
        "surum": layout.manifest.version if layout else "",
        "aciklama": layout.manifest.description if layout else "",
        "yazar": layout.manifest.author if layout else "",
        "bilesenler": _components(layout) if layout else {},
        "kanca_sayisi": report.hook_count,
        "kancalar": list(report.hook_lines),
        "kancalar_calismaz": bool(layout and layout.has_hooks) and not PLUGIN_HOOKS_ACTIVE,
        "mcp": [{"ad": s.name, "hedef": server_target(s, root)} for s in report.servers],
        "calistirilabilir": bool(layout and layout.is_executable),
        "baglam_maliyeti": preview.context_tokens,
        "karma": preview.digest,
        "commit": preview.commit[:12],
        "uyarilar": list(report.warnings),
        "hatalar": list(report.errors),
    }


def _list() -> dict[str, Any]:
    state = load_state()
    return {
        "ok": True,
        "hepsi_kapali": state.all_disabled,
        "eklentiler": [_installed(item) for item in installed_plugins()],
        "pazarlar": [{"ad": m.name, "kaynak": m.source, "tur": m.kind} for m in state.marketplaces],
    }


def _install(data: Mapping[str, object]) -> dict[str, Any]:
    source = _text(data, "kaynak")
    if not source:
        return {"ok": False, "metin": NEEDS_SOURCE}
    approved = data.get("onay") is True
    seen: list[dict[str, Any]] = []

    def approve(preview: plugins.PluginPreview) -> bool:
        seen.append(_preview(preview))
        return approved or not preview.is_executable

    try:
        item = plugins.install_plugin(
            source, approve=approve, expected_digest=_text(data, "beklenen_karma")
        )
    except PluginError as error:
        if seen and seen[0]["calistirilabilir"] and not approved:
            return {"ok": False, "onay_gerekli": True, "metin": NEEDS_APPROVAL, "onizleme": seen[0]}
        return {"ok": False, "metin": str(error)}
    return {"ok": True, "yenile": True, "eklenti": _installed(item)}


def _plugin_action(name: str, data: Mapping[str, object]) -> dict[str, Any]:
    plugin = _text(data, "ad")
    if name == "eklenti.etkinlik":
        enabled = data.get("etkin") is True
        if data.get("hepsi") is True:
            # Claude `disable --all` her eklentiyi ayrı kapatır (#409).
            if enabled:
                plugins.set_all_disabled(False)
            else:
                plugins.disable_all_plugins()
        elif plugin:
            plugins.set_plugin_enabled(plugin, enabled, scope=_text(data, "kapsam"))
        else:
            return {"ok": False, "metin": NEEDS_NAME}
        return {**_list(), "yenile": True}
    if not plugin:
        return {"ok": False, "metin": NEEDS_NAME}
    if name == "eklenti.kaldir":
        plugins.uninstall_plugin(plugin, keep_data=data.get("veriyi_koru") is True)
        return {**_list(), "yenile": True}
    return _trust(plugin, data)


def _trust(plugin: str, data: Mapping[str, object]) -> dict[str, Any]:
    """Ölçüldü (31 Ekim): "Yeniden onayla" tek tıkla `onay: true` yolluyor, değişen içerik
    (yeni kanca/MCP) hiç gösterilmeden çalıştırılabilir oluyordu. Onaysız çağrı önizleme döner."""
    seen: list[dict[str, Any]] = []
    approved = data.get("onay") is True

    def approve(preview: plugins.PluginPreview) -> bool:
        seen.append(_preview(preview))
        return approved

    try:
        plugins.trust_plugin(plugin, approve=approve, expected_digest=_text(data, "beklenen_karma"))
    except PluginError as error:
        if seen and not approved:
            return {
                "ok": False,
                "onay_gerekli": True,
                "metin": NEEDS_REAPPROVAL,
                "onizleme": seen[0],
            }
        return {"ok": False, "metin": str(error)}
    return {**_list(), "yenile": True}


def _update(data: Mapping[str, object]) -> dict[str, Any]:
    """`eklenti.guncelle`: kurulumla aynı onay/karma kapıları; içerik aynıysa `guncel: true`."""
    plugin = _text(data, "ad")
    if not plugin:
        return {"ok": False, "metin": NEEDS_NAME}
    approved = data.get("onay") is True
    seen: list[dict[str, Any]] = []

    def approve(preview: plugins.PluginPreview) -> bool:
        seen.append(_preview(preview))
        return approved or not preview.is_executable

    try:
        result = plugin_update.update_plugin(
            plugin, approve=approve, expected_digest=_text(data, "beklenen_karma")
        )
    except PluginError as error:
        if seen and seen[0]["calistirilabilir"] and not approved:
            return {"ok": False, "onay_gerekli": True, "metin": NEEDS_APPROVAL, "onizleme": seen[0]}
        return {"ok": False, "metin": str(error)}
    return {**_list(), "yenile": result.changed, "guncel": not result.changed}


def _validate(data: Mapping[str, object]) -> dict[str, Any]:
    """`eklenti.dogrula` (CLI `fusion eklenti dogrula <ad>`): bildirim/bileşen/bütünlük raporu."""
    record = load_state().plugin(_text(data, "ad"))
    if record is None:
        return {"ok": False, "metin": plugins.ERR_NOT_INSTALLED.format(name=_text(data, "ad"))}
    report = validate_plugin(plugin_folder(record))
    item = inspect_plugin(record)
    return {
        "ok": True,
        "ad": record.name,
        "gecerli": report.ok,
        "hatalar": list(report.errors),
        "uyarilar": list(report.warnings),
        "butunluk": item.status,
        "ayrinti": item.detail,
    }


def _market(name: str, data: Mapping[str, object]) -> dict[str, Any]:
    if name == "eklenti.kesfet":
        entries = plugins.browse(_text(data, "pazar"))
        return {
            "ok": True,
            "eklentiler": [
                {
                    "ad": e.entry.name,
                    "pazar": e.marketplace,
                    "surum": e.entry.version,
                    "aciklama": e.entry.description,
                    "kurulu": e.installed,
                }
                for e in entries
            ],
        }
    if name == "eklenti.pazar_ekle":
        source = _text(data, "kaynak")
        if not source:
            return {"ok": False, "metin": NEEDS_SOURCE}
        plugins.add_marketplace(source)
    elif name == "eklenti.pazar_guncelle":
        from ..tools.plugin_market_sync import sync_by_name

        plugin_update.update_marketplace(_text(data, "ad"))
        notes = sync_by_name(_text(data, "ad"))  # #397: renames / forceRemoveDeletedPlugins
        return {**_list(), "notlar": list(notes)}
    else:
        # Claude gibi pazar, ondan kurulan eklentiler ve verileri birlikte gider (#396);
        # arayüz onay ister ve kaldırılanları bildirir.
        removed = plugins.remove_marketplace(_text(data, "ad"))
        return {**_list(), "yenile": bool(removed), "kaldirilan": list(removed)}
    return _list()


def _plan_payload(plan: ImportPlan) -> dict[str, Any]:
    return {
        "ok": True,
        "kaynak": plan.source,
        "ogeler": [
            {
                "tur": item.kind.value,
                "ad": item.name,
                "durum": item.status.value,
                "ayrinti": item.detail,
                "dosya": item.origin,
            }
            for item in plan.items
        ],
        "uyarilar": list(plan.warnings),
        "eklenecek": len(plan.pending),
    }


def _import(name: str, data: Mapping[str, object], context: ExtensionContext) -> ExtensionResult:
    plan = build_plan(
        _text(data, "kaynak"), home=context.home, root=context.root, config=context.config
    )
    if name == "ice_aktar.onizle":
        return ExtensionResult(_plan_payload(plan))
    config, report = apply_plan(
        plan, config=context.config, root=context.root, secrets=default_secrets()
    )
    payload = {
        "ok": not report.failed,
        "uygulanan": len(report.applied),
        "hatalar": [{"ad": item.name, "neden": reason} for item, reason in report.failed],
        "yazilan": [str(path) for path in report.written],
        "yenile": bool(report.applied),
    }
    return ExtensionResult(payload, config if config is not context.config else None)


def _release_notes(data: Mapping[str, object]) -> dict[str, Any]:
    path = changelog_path()
    sections = load_sections(path) or ()
    return {
        "ok": True,
        "kurulu": __version__,
        "metin": release_notes_text(_text(data, "surum"), path=path),
        "bolumler": [
            {"baslik": s.title, "surum": s.version, "tarih": s.date} for s in sections[:30]
        ],
    }


def _with_plugin_servers(payload: dict[str, Any], context: ExtensionContext) -> ExtensionResult:
    """Eklenti değişikliğini oturumun MCP kayıtlarına yansıt (kapanan sunucu hemen düşer)."""
    if payload.get("ok") is not True:
        return ExtensionResult(payload)
    updated = refresh_plugin_mcp_servers(context.config)
    if updated == context.config:
        return ExtensionResult(payload)
    current = {s.name: s for s in updated.mcp_servers if s.scope is McpScope.PLUGIN}
    dropped = tuple(
        s.name
        for s in context.config.mcp_servers
        if s.scope is McpScope.PLUGIN and current.get(s.name) != s
    )
    return ExtensionResult(payload, updated, dropped)


def _dispatch_sync(
    name: str, data: Mapping[str, object], context: ExtensionContext
) -> ExtensionResult:
    try:
        if name == "eklenti.listele":
            return ExtensionResult(_list())
        if name == "eklenti.onizle":
            source = _text(data, "kaynak")
            if not source:
                return ExtensionResult({"ok": False, "metin": NEEDS_SOURCE})
            return ExtensionResult(
                {"ok": True, "onizleme": _preview(plugins.preview_plugin(source))}
            )
        if name == "eklenti.kur":
            return _with_plugin_servers(_install(data), context)
        if name in {"eklenti.etkinlik", "eklenti.kaldir", "eklenti.guven"}:
            return _with_plugin_servers(_plugin_action(name, data), context)
        if name == "eklenti.guncelle":
            return _with_plugin_servers(_update(data), context)
        if name == "eklenti.dogrula":
            return ExtensionResult(_validate(data))
        if name.startswith("eklenti."):
            return ExtensionResult(_market(name, data))
        if name.startswith("ice_aktar."):
            return _import(name, data, context)
        return ExtensionResult(_release_notes(data))
    except (PluginError, ConfigError) as error:
        return ExtensionResult({"ok": False, "metin": str(error)})


async def dispatch_extension(
    name: str, data: Mapping[str, object], context: ExtensionContext
) -> ExtensionResult:
    """Tek giriş; git klonu ve dosya taraması olay döngüsünü bloklamasın diye thread'de."""
    if name not in EXTENSION_ROUTES:
        return ExtensionResult({"ok": False, "metin": "Bilinmeyen eklenti isteği."})
    return await asyncio.to_thread(_dispatch_sync, name, data, context)

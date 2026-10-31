"""Masaüstü RPC'leri: içe aktarma ve sürüm notları (P-071).

    ice_aktar.onizle {kaynak} | ice_aktar.uygula {kaynak}
    surum.notlari {surum?}

CLI ve REPL ile aynı işlevleri çağırır. Yanıtta `yenile: true` varsa oturum beceri kataloğunu
yeniden tarar. Sır değeri hiçbir yanıtta yer almaz.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import __version__
from ..config.importers import ImportPlan, apply_plan, build_plan, default_secrets
from ..config.models import Config
from ..config.release_notes import changelog_path, load_sections, release_notes_text
from ..core.errors import ConfigError

EXTENSION_ROUTES = frozenset(
    {
        "ice_aktar.onizle",
        "ice_aktar.uygula",
        "surum.notlari",
    }
)


@dataclass(frozen=True, slots=True)
class ExtensionContext:
    root: Path
    home: Path
    config: Config


@dataclass(frozen=True, slots=True)
class ExtensionResult:
    payload: dict[str, Any]
    #: İçe aktarma MCP kayıtlarını değiştirdiyse yeni yapılandırma.
    config: Config | None = None


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


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


def _dispatch_sync(
    name: str, data: Mapping[str, object], context: ExtensionContext
) -> ExtensionResult:
    try:
        if name.startswith("ice_aktar."):
            return _import(name, data, context)
        return ExtensionResult(_release_notes(data))
    except ConfigError as error:
        return ExtensionResult({"ok": False, "metin": str(error)})


async def dispatch_extension(
    name: str, data: Mapping[str, object], context: ExtensionContext
) -> ExtensionResult:
    """Tek giriş; git klonu ve dosya taraması olay döngüsünü bloklamasın diye thread'de."""
    if name not in EXTENSION_ROUTES:
        return ExtensionResult({"ok": False, "metin": "Bilinmeyen istek."})
    return await asyncio.to_thread(_dispatch_sync, name, data, context)

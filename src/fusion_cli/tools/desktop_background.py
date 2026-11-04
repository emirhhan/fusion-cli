"""Arka plandaki belirli pencereye bağlı gözlem ve erişilebilirlik araçları."""

from __future__ import annotations

import json

from ..core.desktop_settings import DesktopSettings
from ..core.tool_content import ToolContent
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import coerce_int
from .desktop_visibility import is_hidden_app
from .native_desktop import SwiftDesktop

WINDOW_PROPERTIES: dict[str, object] = {
    "window_id": {
        "type": "integer",
        "description": "desktop_window_focus / desktop_background_windows ile doğrulanan kimlik.",
    },
    "pid": {
        "type": "integer",
        "description": "Aynı gözlemde window_id ile birlikte dönen süreç kimliği; birlikte kullan.",
    },
}
BACKGROUND_TOOL_SCHEMAS: dict[str, dict[str, object]] = {
    "desktop_background_windows": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "desktop_background_inspect": {
        "type": "object",
        "properties": WINDOW_PROPERTIES,
        "required": ["window_id", "pid"],
        "additionalProperties": False,
    },
    "desktop_background_screenshot": {
        "type": "object",
        "properties": WINDOW_PROPERTIES,
        "required": ["window_id", "pid"],
        "additionalProperties": False,
    },
    "desktop_background_action": {
        "type": "object",
        "properties": {
            **WINDOW_PROPERTIES,
            "ref": {"type": "string", "description": "Son incelemede dönen öğe başvurusu."},
            "action": {"type": "string", "enum": ["press", "set_value"]},
            "value": {"type": "string", "description": "Yalnız set_value için yeni alan değeri."},
        },
        "required": ["window_id", "pid", "ref", "action"],
        "additionalProperties": False,
    },
}


def _target(args: ToolArgs) -> dict[str, object] | None:
    window, pid = coerce_int(args.get("window_id")), coerce_int(args.get("pid"))
    if window is None or pid is None:
        return None
    if window <= 0 or pid <= 0:
        return None
    return {"kind": "window", "id": window, "pid": pid}


def _visible_windows(result: dict[str, object], settings: DesktopSettings) -> None:
    """Reddedilen/engelli uygulamaların pencereleri listeden çıkar (P-007; başlıklar sızmasın)."""
    windows = result.get("windows")
    if isinstance(windows, list):
        result["windows"] = [
            row
            for row in windows
            if not (isinstance(row, dict) and is_hidden_app(settings, str(row.get("app") or "")))
        ]


async def _invoke(
    operation: str, args: ToolArgs, settings: DesktopSettings | None = None
) -> ToolResult:
    target = {} if operation == "list" else _target(args)
    if target is None:
        return ToolResult.failure("Geçerli window_id ve pid gerekli.")
    if operation == "action":
        ref, action = args.get("ref"), args.get("action")
        value = args.get("value")
        value = "" if value is None else value
        if not isinstance(ref, str) or not ref or len(ref) > 50_000:
            return ToolResult.failure("Son incelemeden bir öğe başvurusu gerekli.")
        if action not in ("press", "set_value") or not isinstance(value, str):
            return ToolResult.failure("Yalnız press ve metin değerli set_value destekleniyor.")
        if len(value) > 10_000:
            return ToolResult.failure("Alan değeri uzunluk sınırını aşıyor.")
        target["request"] = {"ref": ref, "action": action, "value": value}
    result = await SwiftDesktop().invoke(operation, target)
    if not result.get("ok"):
        message = str(result.get("metin", "Hedef pencereye erişilemedi."))
        checks = result.get("action_checks")
        if operation == "action" and isinstance(checks, dict):
            safe_checks = {
                key: checks[key]
                for key in (
                    "tree_complete",
                    "fingerprint_matches",
                    "identity_unique",
                    "path_identity_matches",
                )
                if type(checks.get(key)) is bool
            }
            raw_kinds = result.get("value_kinds")
            kinds = raw_kinds if isinstance(raw_kinds, dict) else {}
            safe_kinds = {
                key: kinds[key]
                for key in (
                    "absent",
                    "string",
                    "boolean",
                    "number",
                    "ax_value",
                    "element",
                    "array",
                    "other",
                )
                if type(kinds.get(key)) is int and 0 <= kinds[key] <= 500
            }
            payload = {
                "ok": False,
                "metin": message,
                "action_checks": safe_checks,
                "value_kinds": safe_kinds,
            }
            return ToolResult.failure(json.dumps(payload, ensure_ascii=False), structured=payload)
        return ToolResult.failure(message)
    if settings is not None:
        _visible_windows(result, settings)
    image = result.pop("image", None)
    content: tuple[ToolContent, ...] = ()
    if isinstance(image, str) and image.startswith("data:image/png;base64,"):
        content = (ToolContent.image("image/png", image.split(",", 1)[1]),)
    return ToolResult(json.dumps(result, ensure_ascii=False), content=content)


async def desktop_background_windows(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Pencereleri kimlik ve süreç kimliğiyle listele (reddedilen uygulamalar hariç)."""
    return await _invoke("list", args, context.desktop_settings)


async def desktop_background_inspect(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Pencereyi öne getirmeden AX ağacını ve eylem başvurularını oku."""
    del context
    return await _invoke("inspect", args)


async def desktop_background_screenshot(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Belirli pencereyi ScreenCaptureKit ile öne getirmeden yakala."""
    del context
    return await _invoke("snapshot", args)


async def desktop_background_action(args: ToolArgs, context: ToolContext) -> ToolResult:
    """İncelenmiş tekil öğeye AXPress veya doğrulanan AXValue uygula."""
    del context
    return await _invoke("action", args)

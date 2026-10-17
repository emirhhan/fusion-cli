"""Arka plandaki belirli pencereye bağlı gözlem ve erişilebilirlik araçları."""

from __future__ import annotations

import json

from ..core.tool_content import ToolContent
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .native_desktop import SwiftDesktop

WINDOW_PROPERTIES: dict[str, object] = {
    "window_id": {"type": "integer", "description": "Pencere listesindeki kararlı kimlik."},
    "pid": {"type": "integer", "description": "Pencereyi tutan uygulamanın süreç kimliği."},
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
    window, pid = args.get("window_id"), args.get("pid")
    if type(window) is not int or type(pid) is not int:
        return None
    if window <= 0 or pid <= 0:
        return None
    return {"kind": "window", "id": window, "pid": pid}


async def _invoke(operation: str, args: ToolArgs) -> ToolResult:
    target = {} if operation == "list" else _target(args)
    if target is None:
        return ToolResult.failure("Geçerli window_id ve pid gerekli.")
    if operation == "action":
        ref, action, value = args.get("ref"), args.get("action"), args.get("value", "")
        if not isinstance(ref, str) or not ref or len(ref) > 50_000:
            return ToolResult.failure("Son incelemeden bir öğe başvurusu gerekli.")
        if action not in ("press", "set_value") or not isinstance(value, str):
            return ToolResult.failure("Yalnız press ve metin değerli set_value destekleniyor.")
        if len(value) > 10_000:
            return ToolResult.failure("Alan değeri uzunluk sınırını aşıyor.")
        target["request"] = {"ref": ref, "action": action, "value": value}
    result = await SwiftDesktop().invoke(operation, target)
    if not result.get("ok"):
        return ToolResult.failure(str(result.get("metin", "Hedef pencereye erişilemedi.")))
    image = result.pop("image", None)
    content: tuple[ToolContent, ...] = ()
    if isinstance(image, str) and image.startswith("data:image/png;base64,"):
        content = (ToolContent.image("image/png", image.split(",", 1)[1]),)
    return ToolResult(json.dumps(result, ensure_ascii=False), content=content)


async def desktop_background_windows(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Pencereleri kimlik ve süreç kimliğiyle listele."""
    del context
    return await _invoke("list", args)


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

"""Arka plandaki belirli pencereye bağlı gözlem ve erişilebilirlik araçları."""

from __future__ import annotations

import json
import time

from ..core.desktop_ref_handles import canonical_arguments, context_scope
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


def _failure_cause(result: dict[str, object]) -> str:
    """Project fixed native diagnostics, never interpret element labels as advice."""
    checks = result.get("action_checks")
    keys = ("tree_complete", "identity_unique", "fingerprint_matches", "path_identity_matches")
    if isinstance(checks, dict) and all(type(checks.get(key)) is bool for key in keys):
        for key, cause in zip(
            keys,
            (
                "tree_incomplete",
                "identity_ambiguous",
                "stale_tree",
                "path_changed",
            ),
            strict=True,
        ):
            if checks[key] is False:
                return cause
    return {
        "macOS Erişilebilirlik izni gerekli.": "permission_required",
        "Hedef pencere kapandı veya kimliği değişti.": "window_missing",
        "Hedef pencerenin erişilebilirlik kimliği doğrulanamadı.": "window_unverified",
        "Öğe AXPress desteklemiyor.": "press_unsupported",
        "Öğe AXValue değiştirmeyi desteklemiyor.": "value_unsupported",
        "Alan değeri doğrulanamadı; işlem tekrarlanmadı.": "value_unverified",
        "Hedef öğe AX işlemini reddetti.": "action_rejected",
    }.get(str(result.get("metin", "")), "unknown")


async def _invoke(
    operation: str,
    args: ToolArgs,
    settings: DesktopSettings | None = None,
    context: ToolContext | None = None,
) -> ToolResult:
    if operation == "action" and context is not None:
        try:
            args = canonical_arguments("desktop_background_action", args, context)
        except ValueError as exc:
            return ToolResult.failure(str(exc))
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
    if operation == "inspect" and context is not None:
        scope = context_scope(context)
        pid, window = coerce_int(target["pid"]), coerce_int(target["id"])
        assert pid is not None and window is not None
        try:
            ticket = context.desktop.ref_handles.begin_inspection(scope, pid, window)
        except ValueError as exc:
            return ToolResult.failure(str(exc))
    native_started = time.monotonic()
    result = await SwiftDesktop().invoke(operation, target)
    native_elapsed_ms = min(600_000, max(0, round((time.monotonic() - native_started) * 1000)))
    if not result.get("ok"):
        message = str(result.get("metin", "Hedef pencereye erişilemedi."))
        diagnostic = (
            {
                "native_failure": {
                    "cause": _failure_cause(result),
                    "operation": operation,
                    "pid": target.get("pid"),
                    "window_id": target.get("id"),
                    "elapsed_ms": native_elapsed_ms,
                }
            }
            if operation in {"inspect", "action"}
            else {}
        )
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
            return ToolResult.failure(
                json.dumps(payload, ensure_ascii=False),
                structured={**payload, **diagnostic},
            )
        return ToolResult.failure(message, structured=diagnostic or None)
    if operation == "inspect" and context is not None:
        if context_scope(context) != scope:
            return ToolResult.failure("Gözlem turu değişti; hedef pencereyi yeniden incele.")
        assert pid is not None and window is not None
        elements = result.get("elements")
        if isinstance(elements, list):
            rows = [
                row for row in elements if isinstance(row, dict) and isinstance(row.get("ref"), str)
            ]
            try:
                aliases = context.desktop.ref_handles.observe(
                    scope,
                    pid,
                    window,
                    [row["ref"] for row in rows],
                    ticket=ticket,
                )
            except ValueError as exc:
                return ToolResult.failure(str(exc))
            # Never mutate the native response retained by diagnostics/test callers.
            replacements = {id(row): alias for row, alias in zip(rows, aliases, strict=True)}
            result = {
                **result,
                "elements": [
                    {**row, "ref": replacements[id(row)]} if id(row) in replacements else row
                    for row in elements
                ],
            }
    if settings is not None:
        _visible_windows(result, settings)
    windows = result.get("windows")
    if operation == "list" and isinstance(windows, list):
        # App icons belong to the native dock, not model/event text. Project
        # fresh rows so native UI consumers retain their binary metadata.
        result = {
            **result,
            "windows": [
                {key: value for key, value in row.items() if key != "icon"}
                if isinstance(row, dict)
                else row
                for row in windows
            ],
        }
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
    return await _invoke("inspect", args, context=context)


async def desktop_background_screenshot(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Belirli pencereyi ScreenCaptureKit ile öne getirmeden yakala."""
    del context
    return await _invoke("snapshot", args)


async def desktop_background_action(args: ToolArgs, context: ToolContext) -> ToolResult:
    """İncelenmiş tekil öğeye AXPress veya doğrulanan AXValue uygula."""
    return await _invoke("action", args, context=context)

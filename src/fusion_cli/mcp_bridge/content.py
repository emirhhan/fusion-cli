"""MCP SDK içeriklerini Fusion'ın kanonik araç sonucuna dönüştür."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from mcp.types import (
    AudioContent,
    BlobResourceContents,
    CallToolResult,
    EmbeddedResource,
    ImageContent,
    ResourceLink,
    TextContent,
    TextResourceContents,
)

from ..core.constants import MAX_OUTPUT_CHARS, truncate_notice
from ..core.tool_content import ToolContent
from ..core.tools import ToolResult


def normalize_call_result(result: CallToolResult) -> ToolResult:
    """SDK sonucunu metin, ikili blok ve yapılandırılmış veri kaybetmeden dönüştür."""
    blocks: list[ToolContent] = []
    priority_lines: list[str] = []
    body_lines: list[str] = []
    for block in result.content:
        _append_block(block, blocks, priority_lines, body_lines)

    structured = _structured_content(getattr(result, "structuredContent", None))
    if structured is not None:
        priority_lines.append("Yapılandırılmış sonuç:\n" + _json_text(structured))

    output = _compose_output(priority_lines, body_lines)
    if not output and blocks:
        output = "[MCP aracı metin dışı içerik döndürdü.]"
    return ToolResult(
        output=output,
        ok=not bool(getattr(result, "isError", False)),
        content=tuple(blocks),
        structured=structured,
    )


def _append_block(
    block: object,
    blocks: list[ToolContent],
    priority_lines: list[str],
    body_lines: list[str],
) -> None:
    if isinstance(block, TextContent):
        blocks.append(ToolContent.text_block(block.text))
        body_lines.append(block.text)
        return
    if isinstance(block, ImageContent):
        blocks.append(ToolContent.image(block.mimeType, block.data))
        priority_lines.append(f"[Görsel: {block.mimeType}]")
        return
    if isinstance(block, AudioContent):
        blocks.append(ToolContent.audio(block.mimeType, block.data))
        priority_lines.append(f"[Ses: {block.mimeType}; ikili veri modele metin olarak eklenmedi]")
        return
    if isinstance(block, ResourceLink):
        uri = str(block.uri)
        blocks.append(
            ToolContent.resource_link(
                uri=uri,
                name=block.name,
                title=block.title or "",
                description=block.description or "",
                mime_type=block.mimeType or "",
                size=block.size,
            )
        )
        ayrinti = [block.title or block.name, uri]
        if block.mimeType:
            ayrinti.append(block.mimeType)
        if block.description:
            ayrinti.append(block.description)
        if block.size is not None:
            ayrinti.append(f"{block.size} bayt")
        priority_lines.append("[Kaynak bağlantısı: " + " · ".join(ayrinti) + "]")
        return
    if isinstance(block, EmbeddedResource):
        _append_resource(block.resource, blocks, priority_lines, body_lines)
        return
    if getattr(block, "type", None) == "text":
        text = getattr(block, "text", "")
        if isinstance(text, str):
            blocks.append(ToolContent.text_block(text))
            body_lines.append(text)
            return
    priority_lines.append(f"[Desteklenmeyen MCP içerik bloğu: {type(block).__name__}]")


def _append_resource(
    resource: TextResourceContents | BlobResourceContents,
    blocks: list[ToolContent],
    priority_lines: list[str],
    body_lines: list[str],
) -> None:
    uri = str(resource.uri)
    mime_type = resource.mimeType or ""
    if isinstance(resource, TextResourceContents):
        blocks.append(ToolContent.resource_text(uri=uri, text=resource.text, mime_type=mime_type))
        priority_lines.append(f"[Gömülü metin kaynağı: {uri}{_mime_suffix(mime_type)}]")
        body_lines.append(resource.text)
        return
    blocks.append(ToolContent.resource_blob(uri=uri, data=resource.blob, mime_type=mime_type))
    priority_lines.append(
        f"[Gömülü ikili kaynak: {uri}{_mime_suffix(mime_type)}; "
        "ikili veri modele metin olarak eklenmedi]"
    )


def _mime_suffix(mime_type: str) -> str:
    return f" · {mime_type}" if mime_type else ""


def _structured_content(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(Mapping[str, object], value)


def _json_text(value: Mapping[str, object]) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(dict(value))


def _compose_output(priority_lines: list[str], body_lines: list[str]) -> str:
    """Metadata ve structured veriye ayrılmış bütçe ver; serbest metni sonra ekle."""
    body = "\n\n".join(body_lines)
    if not priority_lines:
        return truncate_notice(body, MAX_OUTPUT_CHARS, ne="MCP araç çıktısı")

    priority_budget = MAX_OUTPUT_CHARS * 2 // 3
    max_items = 64
    selected = priority_lines[:max_items]
    if len(priority_lines) > max_items:
        selected = [
            *priority_lines[: max_items - 2],
            f"[… {len(priority_lines) - max_items + 1} öncelikli MCP bloğu gösterilmedi.]",
            priority_lines[-1],
        ]
    separators = 2 * (len(selected) - 1)
    item_budget = max(1, (priority_budget - separators) // len(selected))
    priority = "\n\n".join(
        _fit_with_notice(item, item_budget, "MCP öncelikli bloğu") for item in selected
    )
    if not body:
        return priority

    remaining = MAX_OUTPUT_CHARS - len(priority) - 2
    return f"{priority}\n\n{_fit_with_notice(body, remaining, 'MCP metin içeriği')}"


def _fit_with_notice(text: str, limit: int, label: str) -> str:
    """Metni verilen kesin bütçeye, görünür kırpma notuyla sığdır."""
    if len(text) <= limit:
        return text
    notice = f"\n[… {label} KIRPILDI.]"
    if limit <= len(notice):
        return notice[:limit]
    return text[: limit - len(notice)] + notice

"""Kullanıcının izin verdiği açık Chrome sekmesine bağlı araçlar."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from ..core.tool_content import ToolContent
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .web import url_block_reason


async def _call(context: ToolContext, name: str, data: dict[str, Any]) -> ToolResult:
    if context.chrome is None:
        return ToolResult.failure(
            "Chrome bağlantısı yalnız Fusion masaüstü uygulamasında kullanılabilir."
        )
    try:
        result = await context.chrome.invoke(name, data)
    except (ConnectionError, TimeoutError) as exc:
        return ToolResult.failure(str(exc))
    if not result.get("ok"):
        return ToolResult.failure(str(result.get("hata") or "Chrome komutu başarısız."))
    return ToolResult(json.dumps(result.get("veri", {}), ensure_ascii=False))


async def chrome_page(_args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bağlı sekmenin başlık, adres, görünür metin ve eylem öğelerini oku."""
    return await _call(context, "snapshot", {})


async def chrome_click(args: ToolArgs, context: ToolContext) -> ToolResult:
    return await _call(context, "click", {"ref": require_str(args, "ref")})


async def chrome_type(args: ToolArgs, context: ToolContext) -> ToolResult:
    return await _call(
        context, "type", {"ref": require_str(args, "ref"), "text": require_str(args, "text")}
    )


async def chrome_navigate(args: ToolArgs, context: ToolContext) -> ToolResult:
    url = require_str(args, "url")
    if not url.startswith(("https://", "http://")):
        url = f"https://{url}"
    reason = url_block_reason(url)
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
    return await _call(context, "navigate", {"url": url})


async def chrome_screenshot(_args: ToolArgs, context: ToolContext) -> ToolResult:
    if context.chrome is None:
        return ToolResult.failure("Chrome eklentisi bağlı değil.")
    try:
        result = await context.chrome.invoke("screenshot", {})
    except (ConnectionError, TimeoutError) as exc:
        return ToolResult.failure(str(exc))
    if not result.get("ok"):
        return ToolResult.failure(str(result.get("hata") or "Ekran görüntüsü alınamadı."))
    data = result.get("veri")
    image = data.get("image") if isinstance(data, dict) else None
    if not isinstance(image, str) or not image.startswith("data:image/jpeg;base64,"):
        return ToolResult.failure("Chrome geçersiz görsel döndürdü.")
    encoded = image.partition(",")[2]
    try:
        decoded = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return ToolResult.failure("Chrome görseli çözülemedi.")
    if len(decoded) > 3_000_000:
        return ToolResult.failure("Chrome görseli çok büyük.")
    return ToolResult(
        "İzinli Chrome sekmesinin ekran görüntüsü.",
        content=(ToolContent.image("image/jpeg", encoded),),
    )

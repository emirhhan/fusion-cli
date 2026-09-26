"""Kullanıcının izin verdiği açık Chrome sekmesine bağlı araçlar."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

from ..core.tool_content import ToolContent
from ..core.tools import ToolArgs, ToolContext, ToolEffect, ToolResult
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


async def chrome_page(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bağlı sekmeyi oku; `query` verilirse metne/etikete göre öğe bul (ref al)."""
    query = args.get("query")
    if isinstance(query, str) and query.strip():
        return await _call(context, "find", {"query": query.strip()})
    return await _call(context, "snapshot", {})


async def chrome_click(args: ToolArgs, context: ToolContext) -> ToolResult:
    return await _call(context, "click", {"ref": require_str(args, "ref")})


async def chrome_type(args: ToolArgs, context: ToolContext) -> ToolResult:
    return await _call(
        context, "type", {"ref": require_str(args, "ref"), "text": require_str(args, "text")}
    )


#: Sayfada kalıcı iz BIRAKMAYAN işlemler: otomatik kipte sorulmaz, plan kipinde serbest.
#: Seçim kutusu değeri yalnız formu değiştirir; gönderme ayrı bir tıklama/Enter'dır.
_READ_ACTIONS = frozenset({"scroll", "wait", "tabs", "open", "tab", "select", "screenshot"})

#: Tıklanınca geri dönüşü zor ya da dışa dönük iş yapan düğme adları (TR/EN).
#: Claude in Chrome da gezinmeyi ve sıradan tıklamayı sormaz; göndermede durur.
_RISKY_CLICK = re.compile(
    r"gönder|paylaş|yayınla|yayımla|\bsil\b|silin|kaldır|satın|ödeme|öde\b|siparişi|onayla|"
    r"kaydet|uygula|etkinleştir|devre dışı|duraklat|yorum yap|yanıtla|takip et|beğen|abone|"
    r"submit|send|\bpost\b|publish|share|delete|remove|buy|purchase|\bpay\b|checkout|"
    r"confirm|save|apply|enable|disable|pause|follow|\blike\b|reply|comment",
    re.IGNORECASE,
)


async def chrome_action_effect(args: ToolArgs, _context: ToolContext | None) -> ToolEffect | None:
    """Kaydırma, bekleme, sekme ve seçim salt okuma sayılır; tuş (Enter formu gönderir) sorulur."""
    return ToolEffect.REMOTE_READ if args.get("action") in _READ_ACTIONS else None


async def chrome_read_effect(_args: ToolArgs, _context: ToolContext | None) -> ToolEffect:
    """Gezinme ve alana yazma kalıcı iz bırakmaz: gönderme ayrı bir eylemdir."""
    return ToolEffect.REMOTE_READ


async def chrome_click_effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
    """Tıklanacak öğenin adına bak: gönder/sil/satın al gibi ise sor, değilse sorma.

    Ad okunamazsa `None` döner ve aracın kendi (sorulan) etkisi geçerli olur.
    """
    ref = args.get("ref")
    if context is None or context.chrome is None or not isinstance(ref, str):
        return None
    try:
        result = await context.chrome.invoke("describe", {"ref": ref})
    except (ConnectionError, TimeoutError):
        return None
    veri = result.get("veri") if result.get("ok") else None
    if not isinstance(veri, dict):
        return None
    ad = f"{veri.get('name', '')} {veri.get('type', '')}"
    if veri.get("submit") or _RISKY_CLICK.search(ad):
        return None
    return ToolEffect.REMOTE_READ


async def chrome_action(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Tek araçta yardımcı sayfa işlemleri (Claude'daki gibi `action` alanıyla)."""
    action = require_str(args, "action")
    ref = args.get("ref")
    value = args.get("value")
    data: dict[str, Any] = {}
    if isinstance(ref, str) and ref:
        data["ref"] = ref
    if action == "scroll":
        data["direction"] = "up" if value == "up" else "down"
        return await _call(context, "scroll", data)
    if action == "wait":
        if not isinstance(value, str) or not value.strip():
            return ToolResult.failure("wait için 'value' alanına beklenecek metni yaz.")
        return await _call(context, "wait", {"text": value, "timeout_ms": 20_000})
    if action == "key":
        data["key"] = value if isinstance(value, str) and value else "Enter"
        return await _call(context, "key", data)
    if action == "screenshot":
        return await chrome_screenshot(args, context)
    if action == "tabs":
        return await _call(context, "tabs", {})
    if action == "open":
        if not isinstance(value, str) or not value.strip():
            return ToolResult.failure("open için 'value' alanına adresi yaz.")
        url = value if value.startswith(("https://", "http://")) else f"https://{value}"
        reason = url_block_reason(url)
        if reason is not None:
            return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
        return await _call(context, "tab_open", {"url": url})
    if action == "tab":
        if not isinstance(value, str) or not value.strip().isdigit():
            return ToolResult.failure(
                "tab için 'value' alanına 'tabs' çıktısındaki sekme id'sini yaz."
            )
        return await _call(context, "tab_select", {"id": int(value)})
    if action == "select":
        if "ref" not in data or not isinstance(value, str):
            return ToolResult.failure("select için 'ref' ve 'value' gerekli.")
        return await _call(context, "select", {**data, "value": value})
    return ToolResult.failure(
        "action: scroll, wait, key, select, tabs, open, tab ya da screenshot olmalı."
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

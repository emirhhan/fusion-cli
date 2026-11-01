"""Chrome eklentisinin geliştirici ve yardımcı işlemleri (P-042, P-043, P-073).

`chrome_action` buradaki işlevlere dağıtır: sayfa konsolu ve ağ istekleri, erişilebilirlik
ağacı, kayıtlı kısayollar, yeni pencere ve sekme grubu. Eklenti çağrısı `chrome._call`
ile aynı yoldan gider; çıktı sır maskesinden geçer (konsolda token/parola sızabilir).
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from ..core.redaction import redact
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .preview_origins import allowed_local
from .web import browser_block_reason

#: Konsol/ağ okumasında tek seferde dönen en çok kayıt.
MONITOR_LIMIT = 50
#: `wait` değeri buysa metin değil ağın boşa düşmesi beklenir. Ölçüldü (31 Ekim): "network",
#: "ağ", "ag" takma adları bir sekme adı/sayfa başlığı olarak beklenen metni sessizce ağ
#: beklemesine çeviriyordu; yalnız `network_idle` ayrılmıştır.
NETWORK_IDLE_VALUES = frozenset({"network_idle"})
#: Konsol değerinin "yalnız hatalar" öneki (`errors` ya da `errors:desen`).
_ERRORS_PREFIX = "errors"
#: Ağ değerinde istek kimliği (`id:17`).
_REQUEST_ID = re.compile(r"^id:\s*(\d+)$", re.IGNORECASE)
#: Sekme grubu değeri: `12,13:Başlık` ya da `12,13`.
_GROUP_VALUE = re.compile(r"^\s*([\d\s,]+?)\s*(?::\s*(.*))?$")

Invoke = Callable[[ToolContext, str, dict[str, Any]], Awaitable[ToolResult]]


def _masked(result: ToolResult) -> ToolResult:
    """Çıktıyı sır maskesinden geçir (konsol iletisi/ağ gövdesi anahtar taşıyabilir)."""
    return ToolResult(redact(result.output), content=result.content) if result.ok else result


async def read_console(value: object, context: ToolContext, call: Invoke) -> ToolResult:
    """`console` → `errors`, `errors:desen` ya da serbest desen (alt dize)."""
    data: dict[str, Any] = {"limit": MONITOR_LIMIT}
    text = value.strip() if isinstance(value, str) else ""
    if text.lower() == _ERRORS_PREFIX or text.lower().startswith(f"{_ERRORS_PREFIX}:"):
        data["only_errors"] = True
        pattern = text.partition(":")[2].strip()
        if pattern:
            data["pattern"] = pattern
    elif text:
        data["pattern"] = text
    return _masked(await call(context, "console", data))


async def read_network(value: object, context: ToolContext, call: Invoke) -> ToolResult:
    """`network` → url deseni ya da `id:N` (tek isteğin gövdesiyle)."""
    text = value.strip() if isinstance(value, str) else ""
    match = _REQUEST_ID.match(text)
    if match is not None:
        return _masked(await call(context, "network", {"request_id": int(match.group(1))}))
    data: dict[str, Any] = {"limit": MONITOR_LIMIT}
    if text:
        data["url_pattern"] = text
    return _masked(await call(context, "network", data))


def tree_args(args: ToolArgs) -> dict[str, Any]:
    """`chrome_page` ağaç parametreleri → eklenti `tree` komutunun verisi."""
    data: dict[str, Any] = {"filter": "interactive" if args.get("tree") == "interactive" else "all"}
    depth = args.get("depth")
    if isinstance(depth, int) and depth > 0:
        data["depth"] = depth
    elif isinstance(depth, str) and depth.strip().isdigit():
        data["depth"] = int(depth)
    ref = args.get("ref")
    if isinstance(ref, str) and ref.strip():
        data["ref"] = ref.strip()
    return data


def format_tree(result: ToolResult) -> ToolResult:
    """Eklentinin ağaç yanıtını modelin okuyacağı düz metne çevir."""
    if not result.ok:
        return result
    try:
        veri = json.loads(result.output)
    except json.JSONDecodeError:
        return result
    if not isinstance(veri, dict) or not isinstance(veri.get("tree"), str):
        return result
    head = f"{veri.get('title', '')} — {veri.get('url', '')}".strip(" —")
    summary = (
        f"({veri.get('filter', 'all')}, derinlik {veri.get('depth', '')}, "
        f"{veri.get('lines', 0)} satır)"
    )
    lines = [head, summary]
    if veri.get("truncated"):
        lines.append(
            "NOT: Ağaç kırpıldı. Daha azını görmek için tree=interactive, bir bölüm için ref "
            "ver ya da depth'i küçült."
        )
    lines.append(veri["tree"])
    return ToolResult("\n".join(lines))


async def run_shortcut(value: object, context: ToolContext, call: Invoke) -> ToolResult:
    """`shortcut` → kayıtlı görevin metni; model onu şimdi yerine getirir."""
    name = value.strip().lstrip("/") if isinstance(value, str) else ""
    if not name:
        return ToolResult.failure(
            "shortcut için 'value' alanına kısayol adını yaz; adları 'shortcuts' ile listele."
        )
    result = await call(context, "shortcut_run", {"name": name})
    if not result.ok:
        return result
    try:
        veri = json.loads(result.output)
    except json.JSONDecodeError:
        return result
    text = veri.get("metin") if isinstance(veri, dict) else None
    if not isinstance(text, str):
        return result
    return ToolResult(
        f"“{veri.get('ad', name)}” kısayolunun görevi (kullanıcının kaydettiği metin; şimdi "
        f"bunu yap):\n{text}"
    )


async def open_window(value: object, context: ToolContext, call: Invoke) -> ToolResult:
    """`window` → yeni pencere; adres verildiyse iç ağ korumasından geçer."""
    if not isinstance(value, str) or not value.strip():
        return await call(context, "window_new", {})
    url = value.strip()
    if not url.startswith(("https://", "http://")):
        url = f"https://{url}"
    reason = browser_block_reason(url, allowed_local(context))
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
    return await call(context, "window_new", {"url": url})


async def group_tabs(value: object, context: ToolContext, call: Invoke) -> ToolResult:
    """`group` → `id,id:başlık`; id'ler 'tabs' çıktısından."""
    match = _GROUP_VALUE.match(value) if isinstance(value, str) else None
    ids = (
        [int(part) for part in match.group(1).split(",") if part.strip().isdigit()]
        if match is not None
        else []
    )
    if not ids:
        return ToolResult.failure(
            "group için 'value' alanına sekme id'lerini ve isteğe bağlı başlığı yaz; "
            "ör. 12,13:Araştırma."
        )
    title = (match.group(2) or "").strip() if match is not None else ""
    return await call(context, "tab_group", {"ids": ids, "title": title})

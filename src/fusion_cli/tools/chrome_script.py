"""Claude in Chrome `javascript_tool` ve `browser_batch` karşılıkları (#432).

- `chrome_javascript`: bağlı sekmenin ANA dünyasında betik çalıştırır, son ifadenin değerini
  (söz verilmişse bekleyerek) JSON metni olarak döndürür. Betik sayfada her şeyi yapabildiği
  için (satın alma yasağını da aşabilir, #422) çağrı `REMOTE_DESTRUCTIVE`'dir: İzinleri atla
  dahil her kipte sorulur ve oturum iznine dönüşmez. Sayfanın CSP'si `unsafe-eval`e izin
  vermiyorsa tarayıcı betiği reddeder; hata olduğu gibi döner.
- `chrome_batch`: birden çok Chrome aracını tek çağrıda SIRAYLA çalıştırır, ilk hatada durur.
  Her öğenin kendi izin denetimi uygulanır (`engines/agent/chrome_batch_approval.py`): deny
  kuralı ya da yasak eylem bütün çağrıyı kapatır, en sıkı öğenin etkisi sorulur.
  Onay öğeler çalışmadan önceki sayfaya göre verilir; önceki öğe gezinir ya da pencere açarsa
  sonraki öğenin etkisi çalışma anında yeniden hesaplanır. Etki her kipte sorulan düzeye
  (`REMOTE_DESTRUCTIVE`: hassas alan, yetki verme) çıktıysa çağrı o öğede durur.

Adlar Fusion'ın `chrome_*` ailesinde kalır (sıkı yüzeyde gizleme, araç ailesi); Claude
adlarına (`javascript_tool`, `browser_batch`) geçiş #431'in işidir.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from functools import cache
from typing import TYPE_CHECKING

from ..core.tool_content import ToolContent
from ..core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from .chrome import _call

if TYPE_CHECKING:
    from .registry import ToolRegistry

SCRIPT_TOOL = "chrome_javascript"
BATCH_TOOL = "chrome_batch"
#: Tek toplu çağrıdaki en fazla öğe.
MAX_BATCH = 20
#: Toplu çağrıda kullanılabilen araçlar (iç içe toplu çağrı yok).
BATCH_TOOLS = frozenset(
    {"chrome_page", "chrome_action", "chrome_click", "chrome_type", "chrome_navigate", SCRIPT_TOOL}
)


async def chrome_javascript(args: ToolArgs, context: ToolContext) -> ToolResult:
    text = args.get("text")
    if not isinstance(text, str) or not text.strip():
        return ToolResult.failure("text boş: çalıştırılacak JavaScript'i ver.")
    result = await _call(context, "javascript", {"code": text})
    if not result.ok:
        return result
    try:
        veri = json.loads(result.output)
    except json.JSONDecodeError:
        return result
    if isinstance(veri, dict) and isinstance(veri.get("error"), str):
        return ToolResult.failure(f"Betik hata verdi: {veri['error']}")
    if isinstance(veri, dict) and "result" in veri:
        note = " (kırpıldı)" if veri.get("truncated") else ""
        return ToolResult(f"{veri['result']}{note}")
    return result


def batch_items(args: ToolArgs) -> tuple[tuple[str, dict[str, object]], ...] | str:
    """`actions` listesini (ad, girdi) çiftlerine çevir; geçersizse hata metni döner."""
    raw = args.get("actions")
    if not isinstance(raw, list) or not raw:
        return "actions boş: [{name, input}] listesi ver."
    if len(raw) > MAX_BATCH:
        return f"Tek toplu çağrıda en çok {MAX_BATCH} eylem olabilir."
    items: list[tuple[str, dict[str, object]]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            return f"{index}. öğe {{name, input}} nesnesi olmalı."
        name, data = item.get("name"), item.get("input", {})
        if name not in BATCH_TOOLS:
            allowed = ", ".join(sorted(BATCH_TOOLS))
            return f"{index}. öğe: '{name}' toplu çağrıda kullanılamaz ({allowed})."
        if not isinstance(data, Mapping):
            return f"{index}. öğe: input nesne olmalı."
        items.append((str(name), dict(data)))
    return tuple(items)


@cache
def _registry() -> ToolRegistry:
    from .builtin import build_registry

    return build_registry()


def batch_tool(name: str) -> Tool | None:
    """Öğenin araç tanımı (onay katmanı da aynı tanımı kullanır)."""
    return _registry().get(name)


#: Çalışma anında etkisi bu düzeye çıkan öğe toplu onayla çalışmaz.
_ESCALATED = ToolEffect.REMOTE_DESTRUCTIVE
ESCALATED_RESULT = (
    "{index}. öğe ({name}): önceki adımdan sonra bu eylem ayrı onay istiyor (hassas alan, yetki "
    "verme ya da okunamayan öğe); toplu çağrı burada durdu. Sayfayı read_page ile oku ve bu "
    "adımı tek başına çağır."
)


async def _effect(tool: Tool, data: ToolArgs, context: ToolContext) -> ToolEffect | None:
    if tool.effect_resolver is None:
        return None
    return await tool.effect_resolver(data, context)


async def chrome_batch(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Öğeleri sırayla çalıştır; etkisi her kipte sorulan düzeye çıkan öğede dur (#432).

    Ölçüldü (1 Kasım, bağımsız inceleme): `[navigate giriş sayfası, form_input parola]`
    onay anında parola alanı henüz yokken sorulmadan geçiyordu.
    """
    items = batch_items(args)
    if isinstance(items, str):
        return ToolResult.failure(items)
    resolved: list[tuple[str, ToolArgs, Tool]] = []
    for index, (name, data) in enumerate(items, start=1):
        tool = batch_tool(name)
        if tool is None:
            return ToolResult.failure(f"{index}. öğe: '{name}' aracı yok.")
        resolved.append((name, data, tool))
    # Onay anındaki sayfa: hiçbir öğe çalışmadan önceki etkiler.
    approved = [await _effect(tool, data, context) for _, data, tool in resolved]
    lines: list[str] = []
    content: list[ToolContent] = []
    for index, (name, data, tool) in enumerate(resolved, start=1):
        if index > 1 and approved[index - 1] is not _ESCALATED:
            if await _effect(tool, data, context) is _ESCALATED:
                lines.append(ESCALATED_RESULT.format(index=index, name=name))
                return ToolResult.failure("\n".join(lines), content=tuple(content))
        outcome = tool.run(data, context)
        result = await outcome if inspect.isawaitable(outcome) else outcome
        content.extend(result.content)
        lines.append(f"[{index}] {name}: {result.output}")
        if not result.ok:
            lines.append(f"{index}. öğede durdu; kalan {len(items) - index} eylem yapılmadı.")
            return ToolResult.failure("\n".join(lines), content=tuple(content))
    return ToolResult("\n".join(lines), content=tuple(content))

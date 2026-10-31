"""`preview_console` / `preview_network`: çalışan önizlemenin konsol ve ağ günlüğü.

Claude Code Browser pane'indeki `read_console_messages` ve `read_network_requests`
karşılığı. Ölçüldü (31 Ekim, P-041): `start_preview` yalnız konsol HATALARINI ilk
açılışta özetliyordu; model "neden boş görünüyor" sorusunda sayfanın hangi isteği
400 aldığını ya da uyarı/log satırlarını göremiyordu. Bu araçlar salt okunurdur,
adres verilmezse en son başlatılan önizlemeye bakar ve yalnız yerel adres kabul eder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...core.tools import Tool, ToolArgs, ToolContext, ToolResult
from ...tools.preview_launch import default_preview_url, is_local_url
from ...tools.preview_log import (
    CaptureOptions,
    PageLog,
    clamp_settle,
    collect_page_log,
    format_console,
    format_network,
)

if TYPE_CHECKING:
    from .loop import AgentDeps

NO_PREVIEW = (
    "Çalışan önizleme yok: önce start_preview çağır ya da `url` ile yerel adres ver "
    "(http://localhost:PORT/...)."
)
NOT_LOCAL_HINT = (
    "Bu araç yalnız yerel (localhost) önizlemeyi okur; dış siteler için browser_open kullan."
)

_COMMON_PROPERTIES = {
    "url": {
        "type": "string",
        "description": "okunacak yerel sayfa (varsayılan: son başlatılan önizleme)",
    },
    "wait_ms": {
        "type": "integer",
        "description": "sayfa yüklendikten sonra ek bekleme (varsayılan 1000, en çok 10000)",
    },
}


def preview_log_tools(deps: AgentDeps) -> tuple[Tool, ...]:
    del deps  # günlük araçları motora bağlı durum tutmaz; imza diğer kayıtlarla aynı
    return (
        Tool(
            name="preview_console",
            description=(
                "Çalışan önizleme sayfasını başsız tarayıcıda açıp KONSOL mesajlarını topla "
                "(log/info/warning/error ve sayfa istisnaları, betik:satır ile). Sayfa boş ya da "
                "bozuk görünüyorsa, 'çalışmıyor' demeden önce bunu çağır."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_COMMON_PROPERTIES,
                    "only_errors": {
                        "type": "boolean",
                        "description": "yalnız hata ve uyarıları listele",
                    },
                },
            },
            run=_run_console,
        ),
        Tool(
            name="preview_network",
            description=(
                "Çalışan önizleme sayfasının AĞ isteklerini listele (durum, yöntem, adres, tür); "
                "başarısız istekler (4xx/5xx, bağlantı hatası) başta gelir. Eksik kaynak, "
                "yanlış API yolu ya da CORS sorununu bulmak için kullan."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_COMMON_PROPERTIES,
                    "only_failed": {
                        "type": "boolean",
                        "description": "yalnız başarısız istekleri listele",
                    },
                },
            },
            run=_run_network,
        ),
    )


async def _collect(args: ToolArgs, context: ToolContext) -> PageLog | ToolResult:
    raw = args.get("url")
    url = raw.strip() if isinstance(raw, str) and raw.strip() else default_preview_url(context.root)
    if url is None:
        return ToolResult.failure(NO_PREVIEW)
    if not is_local_url(url):
        return ToolResult.failure(NOT_LOCAL_HINT)
    return await collect_page_log(url, CaptureOptions(settle_ms=clamp_settle(args.get("wait_ms"))))


async def _run_console(args: ToolArgs, context: ToolContext) -> ToolResult:
    log = await _collect(args, context)
    if isinstance(log, ToolResult):
        return log
    text = format_console(log, only_errors=bool(args.get("only_errors")))
    return ToolResult(f"{log.url}\n{text}", ok=not log.error)


async def _run_network(args: ToolArgs, context: ToolContext) -> ToolResult:
    log = await _collect(args, context)
    if isinstance(log, ToolResult):
        return log
    text = format_network(log, only_failed=bool(args.get("only_failed")))
    return ToolResult(f"{log.url}\n{text}", ok=not log.error)

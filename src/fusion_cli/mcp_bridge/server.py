"""MCP SUNUCUSU — Fusion'ın araçlarını başka AI uygulamalarına açar.

`fusion mcp` çalıştırıldığında, Fusion'ın araçları (kod arama, dosya okuma, dizin
listeleme, glob…) resmî **Model Context Protocol** üzerinden bir prize konur. MCP
destekleyen her istemci (Claude masaüstü, Cursor, Cline…) bu prize takılıp Fusion'ın
araçlarını kullanabilir.

Güvenlik: VARSAYILAN olarak yalnızca DEĞİŞTİRMEYEN (salt-okunur) araçlar açılır —
dışarıdan gelen bir istemciye shell/dosya-yazma vermek risklidir. Değiştirici araçları
açmak `--write` ile bilinçli bir adımdır.

`mcp` paketi opsiyoneldir (`fusion-cli[mcp]`); yoksa `fusion mcp` anlaşılır hata verir.

Bilgisayar kullanımı (P-006/P-007): `desktop.enabled: false` ise `desktop_*` ailesi hiç
sunulmaz; açıkken her masaüstü çağrısı Fusion'ın politikasından geçer (ret listesi, engelli
kategori, kademe). MCP'de kullanıcıya soramadığımız için hedef okunamayan, ilk kez kullanılan
uygulama onayı dış istemciye bırakılır ama riskli eylem (gönder/sil, Terminal'de Enter) ve
hedefi doğrulanamayan eylem çalıştırılmaz. Ölçüldü (31 Ekim): sunucu boş `ToolContext` ile
kuruluyor, bu kuralların hiçbiri uygulanmıyordu.
"""

from __future__ import annotations

from pathlib import Path

import mcp.types as mcp_types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from ..config.loader import load_config
from ..core.desktop_settings import DesktopLevel, DesktopSettings
from ..core.errors import FusionError
from ..core.tools import ToolArgs, ToolContext, ToolFamily, ToolResult, tool_family
from ..tools import ToolRegistry, build_registry, desktop_policy

#: Masaüstü politikasının MCP çağrısını kapattığı durumların metni.
DESKTOP_REFUSED = "Masaüstü eylemi yapılmadı: {reason}."
UNKNOWN_TARGET_REASON = (
    "hedef uygulama okunamadı (Erişilebilirlik izni?); reddedilen uygulamalar denetlenemedi"
)
RISKY_REASON = "{reason}; Fusion MCP üzerinden bunu soramaz, kullanıcı kendisi yapmalı"


def load_desktop_settings() -> DesktopSettings:
    """Kullanıcının `desktop:` ayarı; yapılandırma okunamazsa güvenli tarafta (kapalı)."""
    try:
        return load_config().desktop
    except FusionError:
        return DesktopSettings(enabled=False)


async def _execute(
    registry: ToolRegistry, name: str, arguments: ToolArgs, context: ToolContext
) -> ToolResult:
    return await registry.execute(name, arguments, context)


async def _desktop_refusal(name: str, arguments: ToolArgs, context: ToolContext) -> str | None:
    """Masaüstü çağrısını kapatma gerekçesi (onay katmanı olmadan politika)."""
    if tool_family(name) is not ToolFamily.DESKTOP:
        return None
    assessment = await desktop_policy.assess(name, arguments, context)
    if assessment is None:
        return None
    if assessment.blocked is not None:
        return DESKTOP_REFUSED.format(reason=assessment.blocked)
    if assessment.target is None and assessment.required is not DesktopLevel.OBSERVE:
        return DESKTOP_REFUSED.format(reason=UNKNOWN_TARGET_REASON)
    if assessment.risky is not None:
        return DESKTOP_REFUSED.format(reason=RISKY_REASON.format(reason=assessment.risky))
    return None


def build_server(
    root: Path,
    *,
    expose_mutating: bool = False,
    desktop_settings: DesktopSettings | None = None,
) -> Server:
    """Fusion araçlarını sunan bir MCP `Server` kur (stdio ile çalıştırılır).

    `expose_mutating=False` (varsayılan) yalnızca salt-okunur araçları açar.
    `desktop_settings` verilmezse varsayılanlar (`run_stdio` kullanıcının ayarını okur).
    """
    registry = build_registry()
    settings = desktop_settings or DesktopSettings()
    context = ToolContext(root=root, desktop_settings=settings)
    exposed = {
        name
        for name in registry.names()
        if (expose_mutating or not _is_mutating(registry, name))
        and (settings.enabled or tool_family(name) is not ToolFamily.DESKTOP)
    }
    server: Server = Server("fusion")

    @server.list_tools()
    async def _list() -> list[mcp_types.Tool]:
        tools = []
        for name in registry.names():
            if name not in exposed:
                continue
            tool = registry.get(name)
            if tool is None:
                continue
            tools.append(
                mcp_types.Tool(
                    name=name,
                    description=tool.description,
                    inputSchema=dict(tool.parameters),
                )
            )
        return tools

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, object]) -> list[mcp_types.TextContent]:
        if name not in exposed:
            return [mcp_types.TextContent(type="text", text=f"Araç sunulmuyor: {name}")]
        refusal = await _desktop_refusal(name, arguments or {}, context)
        if refusal is not None:
            raise RuntimeError(refusal)
        result = await _execute(registry, name, arguments or {}, context)
        if not result.ok:
            # SDK, işleyiciden çıkan istisnayı `isError=True` sonucuna çevirir; düz
            # metin dönmek dış istemciye hatayı başarı gibi gösterirdi.
            raise RuntimeError(result.output or f"Araç başarısız: {name}")
        return [mcp_types.TextContent(type="text", text=result.output)]

    return server


def _is_mutating(registry: object, name: str) -> bool:
    tool = registry.get(name)  # type: ignore[attr-defined]
    return bool(tool and tool.mutating)


async def run_stdio(root: Path, *, expose_mutating: bool = False) -> None:
    """MCP sunucusunu stdio üzerinden çalıştır (istemci süreci başlatır)."""
    server = build_server(
        root, expose_mutating=expose_mutating, desktop_settings=load_desktop_settings()
    )
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":  # `python -m fusion_cli.mcp_bridge.server <kök> [--write]`
    import asyncio
    import sys

    _root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    _write = "--write" in sys.argv[2:]
    asyncio.run(run_stdio(_root, expose_mutating=_write))

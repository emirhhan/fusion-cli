"""WordPress MCP adaptörünün tek "yetenek çalıştır" aracı için ÇAĞRI BAZLI etki.

WordPress'in `mcp-adapter` eklentisi sitedeki bütün yetenekleri (WooCommerce
ürün/sipariş, dosya, PHP…) tek bir `mcp-adapter-execute-ability` aracından
çalıştırır ve o aracın MCP işareti `destructiveHint=True`dur. Etki araçtan
okunursa otomatik kip ürün aramayı bile sorar, plan kipi okumayı engeller —
ölçüldü (26 Eylül, Ornekmagaza/WordPress MCP, 63 yetenek).

Her yeteneğin kendi işareti `mcp-adapter-get-ability-info` çıktısında
`meta.annotations` içindedir (`readonly`, `destructive`). Çözücü yetenek başına
BİR KEZ sorar ve önbelleğe alır. Bilgi alınamazsa `None` döner ve karar aracın
kendi (en sıkı) etkisine kalır: belirsizlikte gevşemek yerine sormak.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from ..core.tools import EffectResolver, ToolArgs, ToolContext, ToolEffect

#: WordPress `mcp-adapter` eklentisinin standart araç adları.
EXECUTE_ABILITY = "mcp-adapter-execute-ability"
ABILITY_INFO = "mcp-adapter-get-ability-info"

AbilityInfo = Callable[[str], Awaitable[Mapping[str, object] | None]]


def effect_from_ability_meta(info: Mapping[str, object] | None) -> ToolEffect | None:
    """`meta.annotations`'tan etkiyi çıkar; işaret yoksa `None`."""
    if not isinstance(info, Mapping):
        return None
    meta = info.get("meta")
    annotations = meta.get("annotations") if isinstance(meta, Mapping) else None
    if not isinstance(annotations, Mapping):
        return None
    if annotations.get("readonly") is True:
        return ToolEffect.REMOTE_READ
    if annotations.get("destructive") is True:
        return ToolEffect.REMOTE_DESTRUCTIVE
    return ToolEffect.REMOTE_WRITE


def ability_gateway_resolver(info: AbilityInfo) -> EffectResolver:
    """`ability_name` argümanına göre etkiyi bulan, önbellekli çözücü."""
    cache: dict[str, ToolEffect | None] = {}

    async def resolve(args: ToolArgs, _context: ToolContext | None = None) -> ToolEffect | None:
        name = args.get("ability_name")
        if not isinstance(name, str) or not name.strip():
            return None
        if name not in cache:
            try:
                cache[name] = effect_from_ability_meta(await info(name))
            except Exception:
                # Ağ/sunucu hatası: karar aracın kendi etkisine kalır ve bir
                # sonraki çağrıda yeniden denenir (hata önbelleğe alınmaz).
                return None
        return cache[name]

    return resolve

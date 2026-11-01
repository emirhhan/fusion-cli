"""MCP araç araması: ertelemeli araç yükleme ve `ToolSearch` aracı (#258).

Claude Code (code.claude.com/docs/en/mcp, "Scale with MCP tool search"): MCP araçları
varsayılan olarak ertelenir; oturum başında yalnız adları görünür, şemaları model
`ToolSearch` ile aradığında yüklenir. `ENABLE_TOOL_SEARCH`:

- boş / `true`: MCP araçları ertelenir
- `auto` / `auto:N`: ertelenecek araçların tanımları bağlam penceresinin %10'undan
  (ya da %N'inden) azsa baştan yüklenir; eşik bir kez aşılınca arama açık kalır
- `false`: hepsi baştan yüklenir

`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` aramayı kapatır. `ToolSearch` reddedilmiş ya da
araç listesinde yoksa MCP araçları baştan yüklenir. Sunucu `alwaysLoad: true` ise
araçları ertelenmez; aracın `_meta["anthropic/alwaysLoad"]` işareti de öyle (sunucu
`alwaysLoad: false` diyorsa o da ertelenir).

Fusion çok sağlayıcılıdır: arama sağlayıcının `defer_loading` alanıyla değil istemci
tarafında yapılır; ertelenen aracın şeması model çağrısına eklenmez, `ToolSearch`
sonucunda tanımı döner ve aynı turun sonraki isteğinden itibaren şemayla sunulur.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from ..core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from .registry import ToolRegistry

__all__ = [
    "TOOL_SEARCH",
    "ToolSearchMode",
    "ToolSearchState",
    "refresh_tool_search",
    "tool_search_mode",
    "tool_search_state",
    "visible_tool_names",
]

TOOL_SEARCH = "ToolSearch"
ENABLE_ENV = "ENABLE_TOOL_SEARCH"
DISABLE_BETAS_ENV = "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS"
DEFAULT_THRESHOLD_PCT = 10
DEFAULT_MAX_RESULTS = 5
#: Model penceresi bilinmiyorsa `auto` eşiği için varsayılan.
DEFAULT_CONTEXT_TOKENS = 200_000
#: Tanım boyutu → belirteç kaba tahmini (karakter / 4).
_CHARS_PER_TOKEN = 4
_FALSE_WORDS = frozenset({"false", "0", "no", "off"})
_TRUE_WORDS = frozenset({"", "true", "1", "yes", "on"})


@dataclass(frozen=True, slots=True)
class ToolSearchMode:
    """`enabled=False`: erteleme yok. `threshold_pct=None`: her zaman ertele."""

    enabled: bool
    threshold_pct: int | None = None


def tool_search_mode(environ: Mapping[str, str] | None = None) -> ToolSearchMode:
    """`ENABLE_TOOL_SEARCH` değerini Claude Code tablosuna göre çöz."""
    env = os.environ if environ is None else environ
    if env.get(DISABLE_BETAS_ENV, "").strip():
        return ToolSearchMode(enabled=False)
    raw = env.get(ENABLE_ENV, "").strip().lower()
    if raw in _FALSE_WORDS:
        return ToolSearchMode(enabled=False)
    if raw == "auto":
        return ToolSearchMode(enabled=True, threshold_pct=DEFAULT_THRESHOLD_PCT)
    if raw.startswith("auto:"):
        value = raw[len("auto:") :]
        if value.isdigit() and 0 <= int(value) <= 100:
            return ToolSearchMode(enabled=True, threshold_pct=int(value))
        return ToolSearchMode(enabled=True, threshold_pct=DEFAULT_THRESHOLD_PCT)
    if raw in _TRUE_WORDS:
        return ToolSearchMode(enabled=True)
    return ToolSearchMode(enabled=True)


@dataclass(slots=True)
class ToolSearchState:
    """Oturumun ertelenebilir araçları ve `ToolSearch` ile yüklenenler (paylaşılan durum)."""

    mode: ToolSearchMode
    #: Baştan yüklenen açıklamanın sınırı (Claude 4096; aramayla yüklenen 16384 kalır).
    upfront_limit: int = 4096
    deferrable: dict[str, str] = field(default_factory=dict)
    loaded: set[str] = field(default_factory=set)
    #: `auto` kipinde eşik bir kez aşıldı mı (aşıldıysa arama açık kalır).
    latched: bool = False

    def set_owner(self, owner: str, names: Iterable[str], previous: Iterable[str]) -> None:
        """Bir kaynağın (sunucunun) ertelenebilir adlarını yenile; kalkanlar düşer."""
        for name in previous:
            self.deferrable.pop(name, None)
            self.loaded.discard(name)
        for name in names:
            self.deferrable[name] = owner

    def hidden(
        self, offered: set[str], registry: ToolRegistry, context_tokens: Callable[[], int | None]
    ) -> set[str]:
        """Bu istekte şeması gönderilmeyecek araçlar."""
        if not self.mode.enabled or TOOL_SEARCH not in offered:
            return set()
        pending = {name for name in self.deferrable if name in offered}
        if not pending:
            return set()
        if self.mode.threshold_pct is not None and not self.latched:
            size = sum(_definition_chars(registry.get(name)) for name in self.deferrable)
            budget = (context_tokens() or DEFAULT_CONTEXT_TOKENS) * self.mode.threshold_pct / 100
            if size / _CHARS_PER_TOKEN < budget:
                return set()
            self.latched = True
        return pending - self.loaded

    def search(self, query: str, registry: ToolRegistry, limit: int) -> list[Tool]:
        """`select:A,B` birebir seçer; aksi halde ad ve açıklamada sözcük arar (`+x` şart)."""
        tools = [tool for name in self.deferrable if (tool := registry.get(name)) is not None]
        text = query.strip()
        if text.lower().startswith("select:"):
            wanted = [part.strip() for part in text[len("select:") :].split(",") if part.strip()]
            by_name = {tool.name.lower(): tool for tool in tools}
            return [by_name[name.lower()] for name in wanted if name.lower() in by_name]
        terms = [term.lower() for term in text.split() if term.strip("+")]
        required = [term[1:] for term in terms if term.startswith("+")]
        optional = [term.lstrip("+") for term in terms]
        scored: list[tuple[int, str, Tool]] = []
        for tool in tools:
            name = tool.name.lower()
            if any(term not in name for term in required):
                continue
            body = tool.description[: self.upfront_limit].lower()
            score = sum(3 * (term in name) + (term in body) for term in optional)
            if score or (required and not optional):
                scored.append((score, tool.name, tool))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [tool for _score, _name, tool in scored[:limit]]


def _definition_chars(tool: Tool | None) -> int:
    if tool is None:
        return 0
    return len(json.dumps(tool.schema(), ensure_ascii=False))


def tool_search_state(registry: ToolRegistry) -> ToolSearchState | None:
    """Defterdeki `ToolSearch` aracının paylaşılan durumu; araç yoksa None."""
    tool = registry.get(TOOL_SEARCH)
    state = getattr(tool.run, "tool_search_state", None) if tool is not None else None
    return state if isinstance(state, ToolSearchState) else None


def visible_tool_names(
    names: set[str] | None,
    registry: ToolRegistry,
    context_tokens: Callable[[], int | None],
) -> set[str] | None:
    """Model isteğine şeması eklenecek adlar: ertelenmiş ve yüklenmemiş MCP araçları düşer.

    `context_tokens` yalnız `auto` eşiği gerekince çağrılır (model kataloğu pahalı olabilir).
    """
    state = tool_search_state(registry)
    if state is None:
        return names
    offered = set(registry.names()) if names is None else set(names)
    hidden = state.hidden(offered, registry, context_tokens)
    if not hidden:
        return names
    return offered - hidden


def refresh_tool_search(registry: ToolRegistry, state: ToolSearchState) -> None:
    """Ertelenen ad listesi değişti: `ToolSearch` açıklamasını yenile; boşsa aracı kaldır."""
    if not state.deferrable:
        if registry.get(TOOL_SEARCH) is not None:
            registry.unregister_remote(TOOL_SEARCH)
        return
    _register(registry, state)


def _register(registry: ToolRegistry, state: ToolSearchState) -> None:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        del context
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult.failure("'query' gerekli: `select:Ad1,Ad2` ya da anahtar sözcükler.")
        limit = _max_results(args.get("max_results"))
        found = state.search(query, registry, limit)
        if not found:
            return ToolResult(output="Eşleşen ertelenmiş araç yok.")
        state.loaded.update(tool.name for tool in found)
        return ToolResult(output=_functions_block(found))

    _run.tool_search_state = state  # type: ignore[attr-defined]
    registry.register_or_replace(
        Tool(
            name=TOOL_SEARCH,
            description=_description(state),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "`select:Ad1,Ad2` adları birebir seçer; anahtar sözcükler ad ve "
                            "açıklamada aranır; `+sözcük` adda geçmeli."
                        ),
                    },
                    "max_results": {
                        "type": "number",
                        "description": f"En çok sonuç (varsayılan {DEFAULT_MAX_RESULTS})",
                    },
                },
                "required": ["query"],
            },
            run=_run,
            effect=ToolEffect.LOCAL,
        )
    )


def _max_results(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 1:
        return DEFAULT_MAX_RESULTS
    return int(value)


def _description(state: ToolSearchState) -> str:
    names = ", ".join(sorted(state.deferrable))
    return (
        "Ertelenmiş MCP araçlarının tam şemasını yükler. Aşağıdaki araçların yalnız adı "
        "biliniyor; çağırmadan önce bu araçla yükle (`select:<ad>` ya da anahtar sözcük). "
        f"Yüklenen araç sonraki istekten itibaren çağrılabilir. Ertelenmiş araçlar: {names}"
    )


def _functions_block(tools: list[Tool]) -> str:
    lines = [
        "<function>"
        + json.dumps(
            {
                "description": tool.description,
                "name": tool.name,
                "parameters": dict(tool.parameters),
            },
            ensure_ascii=False,
        )
        + "</function>"
        for tool in tools
    ]
    return "<functions>\n" + "\n".join(lines) + "\n</functions>"

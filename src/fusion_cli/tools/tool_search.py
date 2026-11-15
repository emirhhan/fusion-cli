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

Model desteği (Claude: Opus 4 / Sonnet 4 / Haiku 4.5 ve sonrası aramayı kullanır, eski
modeller araçları baştan yükler ve `true` bunu ezmez): değişken boşken Fusion yalnız 4.
nesil ve sonrası Claude modellerinde erteler; Claude dışı modeller (Gemini, yerel…)
araçları baştan alır. `ENABLE_TOOL_SEARCH` açıkça verilmişse Claude dışı modelde de
ertelenir (arama istemci tarafında yapıldığı için her model kullanabilir).

Fusion çok sağlayıcılıdır: arama sağlayıcının `defer_loading` alanıyla değil istemci
tarafında yapılır; ertelenen aracın şeması model çağrısına eklenmez, `ToolSearch`
sonucunda tanımı döner ve aynı turun sonraki isteğinden itibaren şemayla sunulur.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from weakref import WeakKeyDictionary

from ..core.tools import Tool, ToolArgs, ToolContext, ToolEffect, ToolResult
from .registry import ToolRegistry

__all__ = [
    "TOOL_SEARCH",
    "ToolSearchMode",
    "ToolSearchState",
    "bind_tool_search",
    "prioritize_tools",
    "prioritized_tool_names",
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
    #: `ENABLE_TOOL_SEARCH` açıkça verildi mi (Claude dışı modelde de ertelemeyi açar).
    explicit: bool = field(default=False, compare=False)


def tool_search_mode(environ: Mapping[str, str] | None = None) -> ToolSearchMode:
    """`ENABLE_TOOL_SEARCH` değerini Claude Code tablosuna göre çöz."""
    env = os.environ if environ is None else environ
    if env.get(DISABLE_BETAS_ENV, "").strip():
        return ToolSearchMode(enabled=False)
    raw = env.get(ENABLE_ENV, "").strip().lower()
    explicit = bool(raw)
    if raw in _FALSE_WORDS:
        return ToolSearchMode(enabled=False, explicit=explicit)
    if raw == "auto":
        return ToolSearchMode(True, DEFAULT_THRESHOLD_PCT, explicit=True)
    if raw.startswith("auto:"):
        value = raw[len("auto:") :]
        pct = int(value) if value.isdigit() and 0 <= int(value) <= 100 else DEFAULT_THRESHOLD_PCT
        return ToolSearchMode(True, pct, explicit=True)
    return ToolSearchMode(enabled=True, explicit=explicit)


#: Araç aramasını kullanmayan eski Claude nesilleri (`claude-3-5-haiku`, `claude-2.1`…).
_OLD_CLAUDE = re.compile(r"claude-(?:instant|[123](?:[.-]\d+)?-)|claude-[123](?:\.\d+)?$")


def model_defers(mode: ToolSearchMode, model: str | None) -> bool:
    """Bu modelde MCP araçları ertelenir mi (model bilinmiyorsa kip belirler)?"""
    if not mode.enabled:
        return False
    if not model:
        return True
    lowered = model.lower()
    if "claude" in lowered:
        return _OLD_CLAUDE.search(lowered) is None
    return mode.explicit


@dataclass(slots=True)
class ToolSearchState:
    """Oturumun ertelenebilir araçları ve `ToolSearch` ile yüklenenler (paylaşılan durum)."""

    mode: ToolSearchMode
    #: Baştan yüklenen açıklamanın sınırı (Claude 4096; aramayla yüklenen 16384 kalır).
    upfront_limit: int = 4096
    deferrable: dict[str, str] = field(default_factory=dict)
    loaded: set[str] = field(default_factory=set)
    recent: list[str] = field(default_factory=list)
    result_limit: int = 12
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
        self,
        offered: set[str],
        registry: ToolRegistry,
        context_tokens: Callable[[], int | None],
        model: str | None = None,
    ) -> set[str]:
        """Bu istekte şeması gönderilmeyecek araçlar."""
        if not self.mode.enabled or TOOL_SEARCH not in offered:
            return set()
        if not model_defers(self.mode, model):
            return {TOOL_SEARCH}
        pending = {name for name in self.deferrable if name in offered}
        if not pending:
            return set()
        if self.mode.threshold_pct is not None and not self.latched:
            size = sum(_definition_chars(registry.get(name)) for name in pending)
            budget = (context_tokens() or DEFAULT_CONTEXT_TOKENS) * self.mode.threshold_pct / 100
            if size / _CHARS_PER_TOKEN < budget:
                return set()
            self.latched = True
        return pending - self.loaded

    def search(
        self,
        query: str,
        registry: ToolRegistry,
        limit: int,
        *,
        permitted: Collection[str] | None = None,
    ) -> list[Tool]:
        """`select:A,B` birebir seçer; aksi halde ad ve açıklamada sözcük arar (`+x` şart)."""
        tools = [
            tool
            for name in self.deferrable
            if (permitted is None or name in permitted) and (tool := registry.get(name)) is not None
        ]
        text = query.strip()
        if text.lower().startswith("select:"):
            wanted = [part.strip() for part in text[len("select:") :].split(",") if part.strip()]
            by_name = {tool.name.lower(): tool for tool in tools}
            return [
                by_name[name.lower()] for name in dict.fromkeys(wanted) if name.lower() in by_name
            ][:limit]
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


_SELECTION_ORDER: WeakKeyDictionary[ToolRegistry, list[str]] = WeakKeyDictionary()


def prioritize_tools(registry: ToolRegistry, names: Iterable[str]) -> None:
    """Prioritize real selected definitions, independently of schema deferral.

    This only orders names that are already registered. Permission and count
    projections still run before schemas or executors are exposed.
    """
    selected = [name for name in dict.fromkeys(names) if registry.get(name) is not None]
    prior = _SELECTION_ORDER.get(registry, [])
    recent = (selected + [name for name in prior if name not in selected])[:12]
    _SELECTION_ORDER[registry] = recent
    state = tool_search_state(registry)
    if state is not None:
        state.recent = list(recent)


def prioritized_tool_names(registry: ToolRegistry) -> tuple[str, ...]:
    state = tool_search_state(registry)
    names = _SELECTION_ORDER.get(registry, state.recent if state is not None else [])
    return tuple(name for name in names if registry.get(name) is not None)


def tool_search_state(registry: ToolRegistry) -> ToolSearchState | None:
    """Defterdeki `ToolSearch` aracının paylaşılan durumu; araç yoksa None."""
    tool = registry.get(TOOL_SEARCH)
    state = getattr(tool.run, "tool_search_state", None) if tool is not None else None
    return state if isinstance(state, ToolSearchState) else None


def visible_tool_names(
    names: set[str] | None,
    registry: ToolRegistry,
    context_tokens: Callable[[], int | None],
    *,
    model: str | None = None,
) -> set[str] | None:
    """Model isteğine şeması eklenecek adlar: ertelenmiş ve yüklenmemiş MCP araçları düşer.

    `context_tokens` yalnız `auto` eşiği gerekince çağrılır (model kataloğu pahalı olabilir).
    """
    state = tool_search_state(registry)
    if state is None:
        return names
    offered = set(registry.names()) if names is None else set(names)
    hidden = state.hidden(offered, registry, context_tokens, model)
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


def bind_tool_search(registry: ToolRegistry, permitted: Callable[[], set[str]]) -> None:
    """Bind metadata to this active registry, including later MCP publication."""
    registry._tool_search_permitted = permitted
    state = tool_search_state(registry)
    if state is not None:
        refresh_tool_search(registry, state)


def _admitted(registry: ToolRegistry) -> set[str] | None:
    callback = registry._tool_search_permitted
    if callback is None:
        return None  # Standalone library use has no engine authority projection.
    try:
        names = callback()
    except Exception:
        # Metadata must fail closed without disclosing exception/configuration data.
        return set()
    return names if TOOL_SEARCH in names else set()


def _register(registry: ToolRegistry, state: ToolSearchState) -> None:
    async def _run(args: ToolArgs, context: ToolContext) -> ToolResult:
        del context
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult.failure("'query' gerekli: `select:Ad1,Ad2` ya da anahtar sözcükler.")
        limit = min(_max_results(args.get("max_results")), state.result_limit)
        found = state.search(query, registry, limit, permitted=_admitted(registry))
        # The callback is fresh; never publish or activate a just-revoked candidate.
        admitted = _admitted(registry)
        found = [tool for tool in found if admitted is None or tool.name in admitted]
        if not found:
            return ToolResult(output="Eşleşen ertelenmiş araç yok.")
        state.loaded.update(tool.name for tool in found)
        selected = [tool.name for tool in found]
        prioritize_tools(registry, selected)
        return ToolResult(output=_functions_block(found))

    _run.tool_search_state = state  # type: ignore[attr-defined]
    registry.register_or_replace(
        Tool(
            name=TOOL_SEARCH,
            description=_description(state, _admitted(registry)),
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
    return min(int(value), 12)


def _description(state: ToolSearchState, permitted: Collection[str] | None = None) -> str:
    names = ", ".join(
        sorted(name for name in state.deferrable if permitted is None or name in permitted)
    )
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

"""`/skills` görünürlük paneli: döngü ve `skillOverrides` kaydı (Claude Code #176).

Claude Code (code.claude.com/docs/en/commands `/skills`; skills "Override skill visibility
from settings"): `/skills` becerileri listeler; Space/Enter seçili becerinin görünürlüğünü
`on → name-only → user-invocable-only → off` döngüsünde değiştirir, Esc kaydeder ve değer
`skillOverrides`'a yazılır. Fusion yüzeyleri:

- TUI: `/skills` uygulama-içi modal; yazılan harfler listeyi süzer, `t` liste maliyetine
  (token) göre sıralar/geri alır, Space ya da Enter döndürür (imleç ve süzgeç korunur), Esc
  kaydeder (`run_tui_panel`).
- Terminal REPL ve masaüstü komutu: numaralı liste; `/skills t` token sıralı, `/skills <metin>`
  süzülmüş liste (numaralar tam listedekiyle aynı), `/skills <n>` döndürür ve kaydeder
  (terminalde modal yok; `/memory <n>` ile aynı desen).
- Masaüstü: kataloğun **Görünürlük** görünümü (`yetenek.gorunurluk_listesi` + `yetenek.gorunurluk`)
  aynı `panel_rows`/`save_changes` işlevlerini kullanır.

`off` beceri katalogdan düşer, ama panel onu da gösterir (yeniden açılabilsin). Eklenti
becerileri `skillOverrides`'tan etkilenmez; panelde listelenmez.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from ...config.models import SkillVisibility
from ...config.skill_overrides_writer import next_visibility, write_skill_overrides
from ...core.errors import ConfigError
from ...engines.agent.skill_cost_report import skill_costs
from ...tools.capabilities import Capability, CapabilityRegistry
from ...tools.capability_overrides import (
    _PLUGIN_SOURCES,
    effective_overrides,
    visibility_of,
)
from ...ui.picker import Choice
from .state import ReplState

PANEL_TITLE = "Beceriler — yaz: süz · t: token sırası · Space/Enter: görünürlük · Esc: kaydet"
HINT = (
    "/skills <n> görünürlüğü döndürür (on → name-only → user-invocable-only → off) ve kaydeder; "
    "/skills t token sırası, /skills <metin> süzer."
)
#: TUI modalının `t` kısayolunun döndürdüğü değer (beceri adı olamaz).
SORT_TOKENS = "\x00sort-tokens"
SORT_WORDS = frozenset({"t", "token", "tokens"})


def _overrides(state: ReplState) -> dict[str, SkillVisibility]:
    return effective_overrides(state.config, state.root, state.home)


def panel_items(state: ReplState) -> tuple[tuple[Capability, SkillVisibility], ...]:
    """Panelde görünen beceriler (kapalılar dahil) ve etkin görünürlükleri."""
    registry = state.capabilities
    if registry is None:
        return ()
    overrides = _overrides(state)
    return tuple(
        (item, visibility_of(item, overrides))
        for item in registry.with_overrides({}).skills()
        if not set(item.source.split("+")) & _PLUGIN_SOURCES
    )


def _tokens(registry: CapabilityRegistry, state: ReplState) -> dict[str, int]:
    costs = skill_costs(registry.with_overrides({}), state.config.memory_dir)
    return {cost.name: cost.listing_tokens for cost in costs}


def _matches(item: Capability, query: str) -> bool:
    needle = query.casefold().strip()
    return not needle or needle in f"{item.name} {item.description}".casefold()


def render_list(state: ReplState, query: str = "", *, by_tokens: bool = False) -> str:
    """Terminal/masaüstü: numaralı liste (görünürlük ve liste maliyetiyle); süz ve sırala."""
    items = panel_items(state)
    if not items or state.capabilities is None:
        return ""
    tokens = _tokens(state.capabilities, state)
    numbered = [
        (index, item, visibility)
        for index, (item, visibility) in enumerate(items, start=1)
        if _matches(item, query)
    ]
    if by_tokens:
        numbered.sort(key=lambda row: -tokens.get(row[1].name, 0))
    if not numbered:
        return ""
    lines = [
        f"{index}. {item.name} [{item.source}] · {visibility.value} · "
        f"~{tokens.get(item.name, 0)} belirteç"
        + (f" — {item.description}" if item.description else "")
        for index, item, visibility in numbered
    ]
    return "\n".join([*lines, HINT])


def panel_rows(state: ReplState) -> list[dict[str, object]]:
    """Masaüstü liste paneli: ada göre sıralı satırlar (ham görünürlük, liste maliyeti)."""
    items = panel_items(state)
    if not items or state.capabilities is None:
        return []
    tokens = _tokens(state.capabilities, state)
    return [
        {
            "ad": item.name,
            "kaynak": item.source,
            "aciklama": item.description,
            "gorunurluk": visibility.value,
            "belirtec": tokens.get(item.name, 0),
        }
        for item, visibility in sorted(items, key=lambda row: row[0].name.casefold())
    ]


def save_changes(state: ReplState, changes: Mapping[str, SkillVisibility]) -> str:
    """`skillOverrides`'a yaz, kataloğu yeni görünürlükle kur; kullanıcı metni döndür."""
    if not changes:
        return "Beceri görünürlüğü değişmedi."
    try:
        path = write_skill_overrides(state.root, changes)
    except ConfigError as error:
        return str(error)
    if state.capabilities is not None:
        state.capabilities = state.capabilities.with_overrides(_overrides(state))
    summary = ", ".join(f"{name}: {value.value}" for name, value in changes.items())
    return f"skillOverrides kaydedildi ({path}): {summary}"


def cycle_index(state: ReplState, word: str) -> str:
    """`/skills <n>`: n. becerinin görünürlüğünü döndür ve hemen kaydet."""
    items = panel_items(state)
    index = int(word)
    if not 1 <= index <= len(items):
        return f"Geçersiz beceri numarası: {word} (1–{len(items)})."
    item, visibility = items[index - 1]
    return save_changes(state, {item.name: next_visibility(visibility)})


def panel_choices(
    state: ReplState, pending: Mapping[str, SkillVisibility], *, by_tokens: bool = False
) -> list[Choice]:
    items = list(panel_items(state))
    tokens = _tokens(state.capabilities, state) if state.capabilities is not None else {}
    if by_tokens:
        items.sort(key=lambda row: -tokens.get(row[0].name, 0))
    return [
        Choice(
            item.name,
            item.name,
            f"{pending.get(item.name, visibility).value} · {item.source} · "
            f"~{tokens.get(item.name, 0)} belirteç",
        )
        for item, visibility in items
    ]


async def run_tui_panel(
    state: ReplState, await_choice: Callable[..., Awaitable[str | None]]
) -> str:
    """TUI modal döngüsü: Space/Enter görünürlüğü döndürür, `t` token sırası, Esc kaydeder."""
    current = {item.name: visibility for item, visibility in panel_items(state)}
    if not current:
        return ""
    pending: dict[str, SkillVisibility] = {}
    by_tokens = False
    cursor: str | None = None
    reopened = False
    while True:
        selected = await await_choice(
            PANEL_TITLE,
            panel_choices(state, pending, by_tokens=by_tokens),
            hotkeys={"t": SORT_TOKENS},
            filterable=True,
            space_selects=True,
            initial=cursor,
            keep_filter=reopened,
        )
        if selected is None:
            break
        reopened = True
        if selected == SORT_TOKENS:
            by_tokens = not by_tokens
            continue
        cursor = selected
        pending = {
            **pending,
            selected: next_visibility(pending.get(selected, current[selected])),
        }
    changes = {name: value for name, value in pending.items() if value != current.get(name)}
    return save_changes(state, changes)

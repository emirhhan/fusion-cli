"""`/skills` görünürlük paneli: döngü ve `skillOverrides` kaydı (Claude Code #176).

Claude Code (code.claude.com/docs/en/commands `/skills`; skills "Override skill visibility
from settings"): `/skills` becerileri listeler; Space/Enter seçili becerinin görünürlüğünü
`on → name-only → user-invocable-only → off` döngüsünde değiştirir, Esc kaydeder ve değer
`skillOverrides`'a yazılır. Fusion yüzeyleri:

- TUI: `/skills` uygulama-içi modal; Enter döndürür, Esc kaydeder (`run_tui_panel`).
- Terminal REPL ve masaüstü komutu: numaralı liste; `/skills <n>` döndürür ve kaydeder
  (terminalde modal yok; `/memory <n>` ile aynı desen).
- Masaüstü RPC `yetenek.gorunurluk` aynı `save_changes`'i çağırır.

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

PANEL_TITLE = "Beceriler — Enter görünürlüğü değiştirir, Esc kaydeder"
HINT = "/skills <n> görünürlüğü döndürür (on → name-only → user-invocable-only → off) ve kaydeder."


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


def render_list(state: ReplState) -> str:
    """Terminal/masaüstü: numaralı liste (görünürlük ve liste maliyetiyle)."""
    items = panel_items(state)
    if not items or state.capabilities is None:
        return ""
    tokens = _tokens(state.capabilities, state)
    lines = [
        f"{index}. {item.name} [{item.source}] · {visibility.value} · "
        f"~{tokens.get(item.name, 0)} belirteç"
        + (f" — {item.description}" if item.description else "")
        for index, (item, visibility) in enumerate(items, start=1)
    ]
    return "\n".join([*lines, HINT])


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


def panel_choices(state: ReplState, pending: Mapping[str, SkillVisibility]) -> list[Choice]:
    items = panel_items(state)
    return [
        Choice(item.name, item.name, f"{pending.get(item.name, visibility).value} · {item.source}")
        for item, visibility in items
    ]


async def run_tui_panel(
    state: ReplState, await_choice: Callable[[str, list[Choice]], Awaitable[str | None]]
) -> str:
    """TUI modal döngüsü: her Enter seçili becerinin görünürlüğünü döndürür, Esc kaydeder."""
    current = {item.name: visibility for item, visibility in panel_items(state)}
    if not current:
        return ""
    pending: dict[str, SkillVisibility] = {}
    while True:
        selected = await await_choice(PANEL_TITLE, panel_choices(state, pending))
        if selected is None:
            break
        pending = {
            **pending,
            selected: next_visibility(pending.get(selected, current[selected])),
        }
    changes = {name: value for name, value in pending.items() if value != current.get(name)}
    return save_changes(state, changes)

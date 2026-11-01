"""Argümansız `/model` seçicisi (Claude Code ModelPicker, #211).

Claude Code'da `/model` argümansız çağrılınca model seçicisi açılır: Enter seçilen modeli
geçerli yapar ve varsayılan olarak kaydeder, `s` yalnız bu oturum içindir, sol/sağ oklar
vurgulu modelin effort düzeyini değiştirir. Seçici bu modülde yüzeyden bağımsızdır:
satır içi REPL `ui.picker.pick`, tam ekran TUI `FusionTui.await_choice` ile sürer; ikisi de
seçilen değeri `<tuş>:<değer>` biçiminde verir (`alt_keys`).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace

from ...config.model_select import set_agent_model
from ...config.models import Config
from ...core.errors import ConfigError
from ...core.reasoning import ReasoningEffort
from ...ui import messages
from ...ui.picker import Choice
from . import model_switch

#: Seçicinin ek tuşları: `s` yalnız oturum, sol/sağ effort.
SESSION_KEY = "s"
EFFORT_DOWN = "left"
EFFORT_UP = "right"
ALT_KEYS = (SESSION_KEY, EFFORT_DOWN, EFFORT_UP)

#: Sol/sağ okların gezdiği düzeyler (Claude Code: low → max); `auto` modele bırakır.
EFFORT_ORDER = tuple(ReasoningEffort)

#: Seçici çağırıcısı: (başlık, seçenekler, ek tuşlar, imlecin başlayacağı değer) → seçim.
Asker = Callable[[str, Sequence[Choice], tuple[str, ...], str], str | None]
AsyncAsker = Callable[[str, Sequence[Choice], tuple[str, ...], str], Awaitable[str | None]]


@dataclass(frozen=True, slots=True)
class PickResult:
    """Seçicinin sonucu; `model` boşsa vazgeçildi."""

    model: str
    effort: ReasoningEffort
    session_only: bool = False


def model_choices(config: Config) -> tuple[Choice, ...]:
    """Etkin agent modeli başta, sonra aday modelleri (tekrarsız)."""
    rows = [Choice(config.agent.model, config.agent.model, messages.MODEL_PICK_CURRENT)]
    seen = {config.agent.model}
    for candidate in config.candidates:
        if candidate.model in seen:
            continue
        seen.add(candidate.model)
        rows.append(Choice(candidate.model, candidate.model, candidate.name))
    return tuple(rows)


def step_effort(current: ReasoningEffort, delta: int) -> ReasoningEffort:
    """Effort düzeyini `delta` kadar kaydır; uçlarda durur (sarmaz)."""
    index = EFFORT_ORDER.index(current) + delta
    return EFFORT_ORDER[max(0, min(len(EFFORT_ORDER) - 1, index))]


def title(effort: ReasoningEffort) -> str:
    return messages.MODEL_PICK_TITLE.format(effort=effort.value)


def split_pick(picked: str) -> tuple[str, str]:
    """`<tuş>:<değer>` → (tuş, değer); ek tuşsuz seçim ("", değer). Model kimliği `:` içerebilir."""
    for key in ALT_KEYS:
        prefix = f"{key}:"
        if picked.startswith(prefix):
            return key, picked[len(prefix) :]
    return "", picked


def run(config: Config, ask: Asker) -> PickResult | None:
    """Seçiciyi sür: oklar effort'u değiştirip seçiciyi aynı satırda yeniden açar."""
    effort = config.runtime.reasoning_effort
    choices = model_choices(config)
    highlight = config.agent.model
    while True:
        picked = ask(title(effort), choices, ALT_KEYS, highlight)
        step = _step(picked, effort)
        if not isinstance(step, tuple):
            return step
        effort, highlight = step


async def run_async(config: Config, ask: AsyncAsker) -> PickResult | None:
    """`run`'un tam ekran TUI eşi (uygulama içi modal asenkron)."""
    effort = config.runtime.reasoning_effort
    choices = model_choices(config)
    highlight = config.agent.model
    while True:
        picked = await ask(title(effort), choices, ALT_KEYS, highlight)
        step = _step(picked, effort)
        if not isinstance(step, tuple):
            return step
        effort, highlight = step


def _step(
    picked: str | None, effort: ReasoningEffort
) -> PickResult | tuple[ReasoningEffort, str] | None:
    """Tek seçimin anlamı: sonuç, vazgeçme ya da (yeni effort, vurgulu değer) ile yeniden aç."""
    if picked is None:
        return None
    key, value = split_pick(picked)
    if key in (EFFORT_DOWN, EFFORT_UP):
        return step_effort(effort, -1 if key == EFFORT_DOWN else 1), value
    return PickResult(value, effort, session_only=key == SESSION_KEY)


def apply(config: Config, result: PickResult) -> tuple[Config, str]:
    """Seçimi uygula: Enter kaydeder, `s` yalnız oturum; effort oturumluk kalır."""
    if result.session_only:
        updated = set_agent_model(config, result.model)
        note = messages.MODEL_PICK_SESSION.format(model=result.model)
    else:
        try:
            updated, note = model_switch.switch_and_save(config, result.model)
        except ConfigError as error:
            return config, str(error)
    if result.effort is not updated.runtime.reasoning_effort:
        updated = replace(updated, runtime=replace(updated.runtime, reasoning_effort=result.effort))
        note = f"{note}\n{messages.EFFORT_APPLIED.format(effort=result.effort.value)}"
    return updated, note

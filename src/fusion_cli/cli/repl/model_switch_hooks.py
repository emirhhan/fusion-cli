"""`/model` komutunun `PreModelSwitch`/`PostModelSwitch` kapısı (#90).

Yalnız oturumun ana (agent) modeli değişince çalışır; judge/aday değişiklikleri Claude'un
oturum modeli değildir. REPL, TUI ve masaüstü aynı `/model` işleyicisini kullanır.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ...engines.agent.hook_expansion import state_hooks
from ...engines.agent.hook_model_switch import post_model_switch, pre_model_switch
from ...ui import messages
from .state import ReplState

if TYPE_CHECKING:
    from ...config.models import Config
    from .commands import ModelCommandResult


def _requested(parts: list[str]) -> str | None:
    if len(parts) == 1:
        return parts[0]  # `/model <ad>`: kullanıcının yazdığı ad
    return parts[1] if len(parts) > 1 and parts[0].lower() == "agent" else None


def apply_model_result(
    state: ReplState,
    parts: list[str],
    result: ModelCommandResult,
    *,
    persist: Callable[[Config], str] | None = None,
) -> str:
    """Komut sonucunu kancalardan geçirerek uygula; kullanıcıya gösterilecek metni döndür.

    `persist` verilirse değişiklik yalnız kapı izin verdikten sonra kalıcı yazılır; metni
    sonucun mesajının yerine geçer (PreModelSwitch reddi diske de yansımaz).
    """
    config, message = result.config, result.message
    before = state.config.agent.model
    after = config.agent.model
    if not result.ok or before == after:
        state.config = config
        return persist(config) if persist is not None and result.ok else message
    session = state_hooks(state)
    requested = _requested(parts)
    gate = pre_model_switch(session, before, after, requested=requested)
    shown = [messages.HOOKS_SYSTEM.format(text=text) for text in gate.messages]
    if gate.refused is not None:
        return "\n".join([*shown, gate.refused])
    state.config = config
    if persist is not None:
        message = persist(config)
    post = post_model_switch(session, before, after, requested=requested)
    shown.extend(messages.HOOKS_SYSTEM.format(text=text) for text in post)
    return "\n".join([message, *shown])

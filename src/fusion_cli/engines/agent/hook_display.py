"""Kök tur boyunca `MessageDisplay` süzgecini kur (#90).

Yalnız etkileşimli oturumda (REPL, TUI, masaüstü) ve olayın kancası tanımlıysa: ekranda
gösterilen asistan metni (akan parçalar ve akışsız nihai cevap) kancadan geçer. `-p`/
`fusion agent` çıktısı (metin, JSON, stream-json) değişmez; alt ajan ve konsey metni
süzülmez (`providers/eventing.py` yalnız ana kanalı süzer).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from ...core import display_filter
from ...core.hooks.events import HookEvent
from ..hooks.message_display import display_opener

if TYPE_CHECKING:
    from .loop import AgentDeps


@contextmanager
def message_display(deps: AgentDeps) -> Iterator[None]:
    session = getattr(deps, "hooks", None)
    if (
        session is None
        or not getattr(deps, "interactive", False)
        or not session.has(HookEvent.MESSAGE_DISPLAY)
    ):
        yield
        return
    turn_id = session.prompt_id or getattr(deps, "attempt_id", None) or uuid.uuid4().hex
    token = display_filter.install(display_opener(session, turn_id))
    try:
        yield
    finally:
        display_filter.reset(token)

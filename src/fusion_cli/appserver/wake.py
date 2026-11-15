"""Masaüstünde boştaki sohbeti uyandıran turlar (#94, #123): verme ve geri alma.

Arka plan raporu, `asyncRewake` kancası ve kabul kipinde gelen oturumlar arası mesaj,
zamanlanmış görev gibi `cron.vadesi_gelenler` ile DÜZ TUR olarak verilir. Arayüz yoklama
başına yalnız ilk görevi gönderir ve gönderemezse (tur başlamış, soru açık) `cron.geri_ver`
ile geri verir; bu yüzden her uyandırma boş olmayan bir kimlikle, tek tek verilir ve geri
verilince kaynağına (bayrak ya da kuyruk) döner. Kullanıcı arada bağlamı tükettiyse geri
konan bayrak yeniden tur üretmez (`AgentLink.take_wake_turns` ile aynı denetim).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..core.session_cron import Source
from ..ui.background_messages import BG_WAKE_TURN, HOOK_WAKE_TURN

if TYPE_CHECKING:
    from ..cli.repl.state import ReplState

#: Uyandırma kimliği öneki: zamanlanmış görev kimlikleriyle çakışmaz.
WAKE_ID_PREFIX = "uyandirma-"
_INBOUND = "gelen"
_REPORT = "rapor"
_HOOK = "kanca"


@dataclass(slots=True)
class WakeDesk:
    """Verilen son uyandırma ve sayaç (oturum başına)."""

    given: dict[str, tuple[str, str]] = field(default_factory=dict)
    sequence: int = 0

    def give(self, state: ReplState) -> list[dict[str, Any]]:
        """Bekleyen ilk uyandırma turu; kalanlar kaynaklarına geri konur."""
        turns = _collect(state)
        if not turns:
            return []
        first, rest = turns[0], turns[1:]
        for kind, text in reversed(rest):
            _restore(state, kind, text)
        self.sequence += 1
        wake_id = f"{WAKE_ID_PREFIX}{self.sequence}"
        self.given = {wake_id: first}
        return [{"id": wake_id, "gorev": first[1], "kaynak": Source.AGENT.value}]

    def give_back(self, state: ReplState, wake_id: str) -> bool:
        """Gönderilemeyen uyandırmayı geri koy; bu kimlik verilmediyse False."""
        item = self.given.pop(wake_id, None)
        if item is None:
            return False
        _restore(state, *item)
        return True


def _collect(state: ReplState) -> list[tuple[str, str]]:
    link = state.agent_link
    if link is None:
        hooks = state.hook_session
        if hooks is None or not hooks.wake_requested:
            return []
        hooks.wake_requested = False
        return [(_HOOK, HOOK_WAKE_TURN)] if hooks.rewake_notes else []
    queued, link.queued_turns = list(link.queued_turns), []
    turns = [(_INBOUND, text) for text in queued]
    for text in link.take_wake_turns(state):
        turns.append((_REPORT if text == BG_WAKE_TURN else _HOOK, text))
    return turns


def _restore(state: ReplState, kind: str, text: str) -> None:
    link = state.agent_link
    if kind == _INBOUND:
        if link is not None:
            link.queued_turns.insert(0, text)
    elif kind == _REPORT:
        if link is not None:
            link.wake_for_delivery = True
    elif state.hook_session is not None:
        state.hook_session.wake_requested = True

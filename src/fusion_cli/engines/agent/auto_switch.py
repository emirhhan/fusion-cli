"""Onay kartında "Yes, and switch to auto mode" — Claude Code ile birebir (#82).

Kaynak: code.claude.com/docs/en/permissions#permission-system ve
permission-modes#switch-permission-modes. Manuel (`default`) ve acceptEdits kiplerinde, auto
kipi kullanılabiliyorsa onay kartı bu seçeneği sunar: çağrı çalışır ve oturum auto kipine
geçer; sonraki eylemler auto kipinin kurallarıyla (denetçi dahil) değerlendirilir.

Oturumun sahibi (REPL/TUI ve masaüstü `ReplState`) `ApprovalMemory.auto_switch`'i bağlar:
`available` auto'nun o an seçilebilir olup olmadığını (`disableAutoMode` yok, kip Manuel ya
da acceptEdits), `switch` kipi değiştirmeyi yapar. Bağlanmamışsa (alt ajan, `fusion run`,
headless) seçenek sunulmaz. Tur ortasındaki geçiş, onaylanan çağrıyı "kapsam değişti" diye
iptal etmesin diye `AutoReviewState.mode_switches` sayacı artırılır; döngü sayacı görünce
onay kapsamını yeniden okur (kip düşüşündeki `trips` gibi).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .approval import ApprovalMemory, ApprovalRequest

#: Satır içi onayda bu seçeneği seçen sözcükler (`a`/`k` kalıcı kural için ayrılmış).
AUTO_SWITCH_WORDS = frozenset({"oto", "otomatik", "auto"})


@dataclass(frozen=True, slots=True)
class AutoSwitch:
    """Oturum sahibinin bağladığı auto geçişi."""

    available: Callable[[], bool]
    switch: Callable[[], None]


def with_auto_offer(request: ApprovalRequest, memory: ApprovalMemory) -> ApprovalRequest:
    """Auto kullanılabiliyorsa isteği "switch to auto mode" seçeneğiyle işaretle."""
    switch = getattr(memory, "auto_switch", None)
    if switch is None or request.critical is not None or not switch.available():
        return request
    return replace(request, offers_auto=True)


def apply_auto_switch(memory: ApprovalMemory) -> None:
    """Oturumu auto kipine geçir; döngü onay kapsamını yeniden okusun diye sayacı artır."""
    switch = getattr(memory, "auto_switch", None)
    if switch is None or not switch.available():
        return
    memory.auto_review.mode_switches += 1
    switch.switch()

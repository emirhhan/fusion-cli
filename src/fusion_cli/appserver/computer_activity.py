""" "Fusion bilgisayarı kullanıyor" göstergesinin olayları (P-033).

Claude CLI computer use bir bildirim gösterir: "Claude is using your computer · press Esc to
stop". Masaüstünde bu sink ilk ön plan eylemiyle (fare/klavye) `BilgisayarKullaniliyor
{aktif: true, esc}` yayar, tur bitince ya da iptal edilince `aktif: false`. Arayüz bunu
sohbetin üstünde bir şerit olarak gösterir (`app/src/computer/ComputerUseIndicator.tsx`).
Ölçüldü (31 Ekim): `masaustu.etkinlik`in arayüzde tüketicisi yoktu; kullanıcı fare kendi
elindeyken ajanın da ekranı kullandığını göremiyordu.
"""

from __future__ import annotations

from collections.abc import Callable

from ..core.desktop_settings import DesktopSettings
from ..core.events import Event, ToolStarted, TurnFinished

COMPUTER_EVENT = "BilgisayarKullaniliyor"
#: Ekranı (işaretçi/klavye) fiilen kullanan araçlar; okuma ve arka plan araçları değil.
FOREGROUND_TOOLS = frozenset(
    {"desktop_mouse", "desktop_click", "desktop_type", "desktop_key", "desktop_scroll"}
)


class ComputerActivityWatch:
    """Olay sinki: ön plan masaüstü eylemini göstergeye çevirir; turda bir kez açar."""

    def __init__(
        self,
        emit: Callable[[dict[str, object]], None],
        settings: Callable[[], DesktopSettings],
    ) -> None:
        self._emit = emit
        self._settings = settings
        self._active = False

    def handle(self, event: Event) -> None:
        if isinstance(event, TurnFinished):
            self.clear()
            return
        if isinstance(event, ToolStarted) and event.name in FOREGROUND_TOOLS and not self._active:
            self._active = True
            self._emit(
                {"olay": COMPUTER_EVENT, "aktif": True, "esc": self._settings().escape_stops}
            )

    def clear(self) -> None:
        """Tur sonu ya da iptal: gösterge kapanır (açık değilse olay yayılmaz)."""
        if self._active:
            self._active = False
            self._emit({"olay": COMPUTER_EVENT, "aktif": False, "esc": False})

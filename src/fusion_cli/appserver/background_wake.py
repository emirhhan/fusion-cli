"""Masaüstü: arka plan olayı boştaki sohbeti uyandırır (#334, #336).

`cron.vadesi_gelenler` yoklaması vadesi gelen görev yoksa ve bekleyen arka plan olayı
(biten iş, `monitor` satırı) varsa düz metin bir uyandırma turu verir. Olayların kendisi
turun ilk model isteğine harness notu olarak girer; arayüz turu gönderemezse olay
kuyrukta kalır, sonraki yoklamada yeniden gelir (`cron.geri_ver` gerekmez).
"""

from __future__ import annotations

from typing import Any

from ..core.background_events import BackgroundEvents
from ..ui import messages

__all__ = ["BACKGROUND_WAKE_ID", "background_wake_tasks"]

BACKGROUND_WAKE_ID = "arka-plan"


def background_wake_tasks(events: BackgroundEvents | None) -> list[dict[str, Any]]:
    """Bekleyen olay varsa tek uyandırma görevi; yoksa boş liste."""
    if events is None or not events.claim_wake():
        return []
    return [
        {
            "id": BACKGROUND_WAKE_ID,
            "gorev": messages.BACKGROUND_WAKE,
            "kaynak": "agent",
            "duz_metin": True,
        }
    ]

"""Masaüstü izin uçları (`izin.masaustu_*`) ve izin eksikliğini arayüze duyuran sink (P-005).

Arayüz `izin.masaustu_durum` ile sidecar'ın gördüğü Erişilebilirlik / Ekran Kaydı durumunu
okur (Tauri tarafındaki `izin_durumu` Fusion.app sürecini sorar; ikisi aynı sorumlu süreç
altında olmalıdır, elle doğrulanır). Bir `desktop_*` aracı izin yüzünden düşünce
`MasaustuIzinGerekli` olayı akar ve arayüz izin kartını açar; aynı izin bir turda bir kez.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from ..core.events import Event, ToolExecuted, ToolOutcome, TurnFinished
from ..tools.desktop_permissions import (
    PERMISSION_KINDS,
    SETTINGS_URLS,
    missing_permission_from_output,
    probe,
    request,
)

DESKTOP_PERMISSION_ROUTES = frozenset({"izin.masaustu_durum", "izin.masaustu_iste"})
PERMISSION_EVENT = "MasaustuIzinGerekli"


def dispatch_desktop_permission(name: str, data: Mapping[str, object]) -> dict[str, object]:
    """`izin.masaustu_durum` → durum; `izin.masaustu_iste{tur}` → sistem istemi + yeni durum."""
    if name == "izin.masaustu_durum":
        return probe().as_dict()
    if name == "izin.masaustu_iste":
        kind = data.get("tur")
        if kind not in PERMISSION_KINDS:
            return {"ok": False, "metin": "tur accessibility ya da screen_recording olmalı."}
        return request(str(kind)).as_dict()
    return {"ok": False, "metin": "Bilinmeyen izin isteği."}


class DesktopPermissionWatch:
    """Olay sinki: izin yüzünden düşen masaüstü aracını `MasaustuIzinGerekli` olayına çevirir."""

    def __init__(self, emit: Callable[[dict[str, object]], None]) -> None:
        self._emit = emit
        self._announced: set[str] = set()

    def handle(self, event: Event) -> None:
        if isinstance(event, TurnFinished):
            self._announced.clear()
            return
        if not isinstance(event, ToolExecuted) or event.outcome is ToolOutcome.OK:
            return
        if not event.name.startswith("desktop_"):
            return
        kind = missing_permission_from_output(event.output)
        if kind is None or kind in self._announced:
            return
        self._announced.add(kind)
        self._emit(
            {
                "olay": PERMISSION_EVENT,
                "tur": kind,
                "arac": event.name,
                "ayar_baglantisi": SETTINGS_URLS[kind],
            }
        )

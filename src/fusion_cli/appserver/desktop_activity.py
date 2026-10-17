"""Ajanın hedefi belli arka plan adımlarını önizlemeye bağlar; ekranı izlemez."""

from __future__ import annotations

from uuid import uuid4

from ..core.events import Event, ToolExecuted, ToolOutcome, ToolStarted, TurnFinished


class DesktopActivity:
    def __init__(self) -> None:
        self._view: dict[str, object] = {"ok": True, "active": False}

    def clear(self) -> None:
        self._view = {"ok": True, "active": False}

    def view(self) -> dict[str, object]:
        return dict(self._view)

    def handle(self, event: Event) -> None:
        if isinstance(event, TurnFinished):
            self.clear()
        elif isinstance(event, ToolStarted):
            self.clear()
            if not event.name.startswith("desktop_background_"):
                return
            window, pid = event.args.get("window_id"), event.args.get("pid")
            if type(window) is not int or type(pid) is not int or window <= 0 or pid <= 0:
                return
            self._view = {
                "ok": True,
                "active": True,
                "activityId": uuid4().hex,
                "target": {"kind": "window", "id": window, "pid": pid},
                "label": "Fusion arka planda çalışıyor",
            }
        elif isinstance(event, ToolExecuted) and event.outcome is not ToolOutcome.OK:
            self.clear()

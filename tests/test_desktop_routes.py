"""Ajan hedefi yakalama sürerken değişirse eski görüntü gösterilemez."""

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from fusion_cli.appserver.desktop_activity import DesktopActivity
from fusion_cli.appserver.desktop_dock import DesktopDock
from fusion_cli.appserver.desktop_routes import dispatch_desktop
from fusion_cli.core.events import ToolStarted


@pytest.mark.parametrize("change", ["clear", "same_target_new_activity"])
async def test_yakalama_sirasinda_islem_degismisse_eski_kare_donmez(change: str) -> None:
    activity = DesktopActivity()
    activity.handle(ToolStarted("desktop_background_inspect", {"window_id": 12, "pid": 34}))
    entered, release = asyncio.Event(), asyncio.Event()

    class Dock:
        async def snapshot(self, target: dict[str, object]) -> dict[str, object]:
            entered.set()
            await release.wait()
            return {"ok": True, "image": "data:image/png;base64,AAAA"}

    dock = cast(DesktopDock, Dock())  # Test çifti yalnız yakalama sınırını sağlar.
    task = asyncio.create_task(
        dispatch_desktop(
            dock, activity, "masaustu.onizleme", {"target": {"kind": "window", "id": 12, "pid": 34}}
        )
    )
    await entered.wait()
    if change == "clear":
        activity.clear()
    else:
        activity.handle(ToolStarted("desktop_background_inspect", {"window_id": 12, "pid": 34}))
    release.set()
    result = await task
    assert result["ok"] is False
    assert "pngBase64" not in result
    assert "image" not in result

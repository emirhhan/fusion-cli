"""Tarayıcı seçimi de kimlikli pending soru olarak geri gelir ve terminalde kapanır."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.appserver.chrome_bridge import ChromeBridge


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["select", "timeout", "cancel"])
async def test_browser_switch_pending_snapshot_has_owned_terminal_lifecycle(terminal):
    bridge = ChromeBridge()
    bridge._devices.touch("work", "İş")
    task = asyncio.create_task(bridge.request_switch(0.02 if terminal == "timeout" else 2.0))
    await asyncio.sleep(0)
    questions = bridge.status()["sorular"]
    try:
        assert len(questions) == 1
        question = questions[0]
        assert question["id"] and question["veri"]["tarayici_sec"] is True
        events = await bridge._events(0)
        assert events["sorular"][0]["id"] == question["id"]
        if terminal == "select":
            assert bridge._select({"cihaz": {"id": "work", "ad": "İş"}, "soru_id": question["id"]})[
                "ok"
            ]
            assert (await task)["deviceId"] == "work"
        elif terminal == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert await task is None
        assert bridge.status()["sorular"] == []
        assert bridge._devices._switch is None
        bridge._devices.selected = None
        assert not bridge._select({"cihaz": {"id": "work", "ad": "İş"}, "soru_id": question["id"]})[
            "ok"
        ]
        assert bridge._devices.selected is None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

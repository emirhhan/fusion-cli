"""İnsan izni komut taşıma süresinden ayrılır ve kendi komutuna bağlıdır."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.appserver import chrome_bridge
from fusion_cli.appserver.chrome_bridge import ChromeBridge


@pytest.mark.asyncio
async def test_human_wait_suspends_network_deadline_and_is_device_bound(monkeypatch):
    monkeypatch.setattr(chrome_bridge, "COMMAND_TIMEOUT_SECONDS", 0.04)
    monkeypatch.setattr(chrome_bridge, "COMMAND_WAIT_POLL_SECONDS", 0.005, raising=False)
    bridge = ChromeBridge()
    bridge._server = object()
    bridge._mark_command_channel_alive("work", "İş")
    bridge._devices.select("work")
    task = asyncio.create_task(bridge.invoke("navigate", {"url": "https://work.test"}))
    try:
        command = await bridge._devices.queue("work").get()
        body = {"id": command["id"], "bekleme_id": "permission-1", "durum": "permission_wait"}
        assert not bridge._progress(body, "personal")["ok"]
        assert bridge._progress(body, "work")["ok"]
        await asyncio.sleep(0.06)
        assert not task.done(), "insan okurken normal 30sn ağ sınırı komutu bitiremez"
        assert not bridge._progress(
            {**body, "bekleme_id": "wrong", "durum": "permission_done"}, "work"
        )["ok"]
        assert bridge._progress({**body, "durum": "permission_done"}, "work")["ok"]
        bridge._pending[command["id"]].set_result({"ok": True})
        assert await task == {"ok": True}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        bridge._server = None


@pytest.mark.asyncio
async def test_cancelled_command_rejects_late_permission_progress(monkeypatch):
    bridge = ChromeBridge()
    bridge._server = object()
    bridge._mark_command_channel_alive("work", "İş")
    task = asyncio.create_task(bridge.invoke("navigate", {}))
    command = await bridge._devices.queue("work").get()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not bridge._progress(
        {"id": command["id"], "bekleme_id": "permission-1", "durum": "permission_done"}, "work"
    )["ok"]
    assert not bridge._pending
    bridge._server = None


@pytest.mark.asyncio
async def test_human_wait_expiry_and_lost_heartbeat_do_not_hang(monkeypatch):
    monkeypatch.setattr(chrome_bridge, "COMMAND_WAIT_POLL_SECONDS", 0.005, raising=False)
    monkeypatch.setattr(chrome_bridge, "HUMAN_PERMISSION_TIMEOUT_SECONDS", 0.025, raising=False)
    bridge = ChromeBridge()
    bridge._server = object()
    bridge._mark_command_channel_alive("work", "İş")
    task = asyncio.create_task(bridge.invoke("navigate", {}))
    command = await bridge._devices.queue("work").get()
    bridge._progress({"id": command["id"], "bekleme_id": "p", "durum": "permission_wait"}, "work")
    try:
        with pytest.raises(TimeoutError, match="İzin bekleme süresi doldu"):
            await task
        assert not bridge._pending
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        bridge._server = None


@pytest.mark.asyncio
async def test_expired_network_deadline_cannot_be_revived_by_late_human_progress(monkeypatch):
    monkeypatch.setattr(chrome_bridge, "COMMAND_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(chrome_bridge, "COMMAND_WAIT_POLL_SECONDS", 0.005)
    bridge = ChromeBridge()
    bridge._server = object()
    bridge._mark_command_channel_alive("work", "İş")
    task = asyncio.create_task(bridge.invoke("navigate", {}))
    command = await bridge._devices.queue("work").get()
    await asyncio.sleep(0.02)
    assert not bridge._progress(
        {"id": command["id"], "bekleme_id": "late", "durum": "permission_wait"}, "work"
    )["ok"]
    with pytest.raises(TimeoutError):
        await task
    bridge._server = None


@pytest.mark.asyncio
async def test_lost_human_wait_heartbeat_expires_owned_command(monkeypatch):
    monkeypatch.setattr(chrome_bridge, "COMMAND_WAIT_POLL_SECONDS", 0.005)
    monkeypatch.setattr(chrome_bridge, "PERMISSION_HEARTBEAT_TIMEOUT_SECONDS", 0.02)
    bridge = ChromeBridge()
    bridge._server = object()
    bridge._mark_command_channel_alive("work", "İş")
    task = asyncio.create_task(bridge.invoke("navigate", {}))
    command = await bridge._devices.queue("work").get()
    assert bridge._progress(
        {"id": command["id"], "bekleme_id": "p", "durum": "permission_wait"}, "work"
    )["ok"]
    with pytest.raises(TimeoutError, match="bağlantısı koptu"):
        await task
    assert not bridge._pending
    bridge._server = None


@pytest.mark.asyncio
async def test_progress_http_and_result_routes_enforce_same_device_owner():
    import httpx

    bridge = ChromeBridge()
    server = await asyncio.start_server(bridge._handle, "127.0.0.1", 0)
    bridge._server = server
    bridge._token = "synthetic-test-token"
    bridge._port = server.sockets[0].getsockname()[1]
    bridge._mark_command_channel_alive("work", "İş")
    bridge._mark_command_channel_alive("personal", "Kişisel")
    bridge._devices.select("work")
    task = asyncio.create_task(bridge.invoke("navigate", {}))
    command = await bridge._devices.queue("work").get()
    headers = {"Authorization": f"Bearer {bridge._token}"}
    address = f"http://127.0.0.1:{bridge._port}"
    own = {"cihaz": {"id": "work", "ad": "İş"}}
    other = {"cihaz": {"id": "personal", "ad": "Kişisel"}}
    body = {"id": command["id"], "bekleme_id": "p", "durum": "permission_wait"}
    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            denied = await client.post(
                f"{address}/progress", headers=headers, json={**body, **other}
            )
            assert not denied.json()["ok"]
            accepted = await client.post(
                f"{address}/progress", headers=headers, json={**body, **own}
            )
            assert accepted.json()["ok"]
            wrong_result = await client.post(
                f"{address}/result",
                headers=headers,
                json={"id": command["id"], "ok": True, **other},
            )
            assert not wrong_result.json()["ok"]
            assert not task.done()
            completed = await client.post(
                f"{address}/result", headers=headers, json={"id": command["id"], "ok": True, **own}
            )
            assert completed.json()["ok"]
        assert (await task)["ok"]
        assert not bridge._command_leases
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        server.close()
        await server.wait_closed()
        bridge._server = None

"""Public auth-flow sınırında rotating token yarışı ve bekleyen iptali."""

from __future__ import annotations

import asyncio
from contextlib import suppress

import httpx

from fusion_cli.mcp_bridge.oauth_flow import OAuthFlowOwner, SerializedOAuth


async def test_ten_expired_flows_reload_after_one_refresh():
    owner = OAuthFlowOwner()
    state = {"generation": 0, "refreshes": 0}
    entered = asyncio.Event()
    release = asyncio.Event()

    class OfflineAuth(httpx.Auth):
        def __init__(self):
            self.generation = state["generation"]

        async def async_auth_flow(self, request):
            if self.generation == 0:
                state["refreshes"] += 1
                entered.set()
                await release.wait()
                state["generation"] = 1
            yield request

    auth = SerializedOAuth(owner.lock_for("offline-profile"), OfflineAuth)

    async def run():
        flow = auth.async_auth_flow(httpx.Request("GET", "https://offline.invalid"))
        try:
            request = await anext(flow)
            with suppress(StopAsyncIteration):
                await flow.asend(httpx.Response(200, request=request))
        finally:
            await flow.aclose()

    tasks = [asyncio.create_task(run()) for _ in range(10)]
    await entered.wait()
    tasks[-1].cancel()
    await asyncio.gather(tasks[-1], return_exceptions=True)
    assert not tasks[0].cancelled()
    release.set()
    await asyncio.gather(*tasks[:-1])
    assert state["refreshes"] == 1
    assert owner.lock_for("offline-profile") is not owner.lock_for("other-profile")


async def test_cancelled_keyring_write_finishes_before_logout_can_clear():
    """İptal edilen thread yazımı çıkıştan sonra token'ı yeniden kaydedemez."""
    import threading

    from mcp.shared.auth import OAuthToken

    from fusion_cli.mcp_bridge.tokens import KeyringTokenStorage

    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    class OfflineKeyring:
        def __init__(self):
            self.values = {}

        def get_password(self, service, account):
            return self.values.get((service, account))

        def set_password(self, service, account, value):
            entered.set()
            release.wait()
            self.values[service, account] = value
            finished.set()

        def delete_password(self, service, account):
            self.values.pop((service, account), None)

    backend = OfflineKeyring()
    storage = KeyringTokenStorage("offline-fixture", backend=backend)
    lock = OAuthFlowOwner().lock_for("offline-profile")

    async def persist():
        async with lock:
            await storage.set_tokens(
                OAuthToken(access_token="offline-fixture", token_type="Bearer")
            )

    write = asyncio.create_task(persist())
    await asyncio.to_thread(entered.wait)
    try:
        write.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not write.done()
        assert lock.locked()
    finally:
        release.set()
        await asyncio.to_thread(finished.wait)
        await asyncio.gather(write, return_exceptions=True)
        async with lock:
            await storage.clear()
    assert await storage.get_tokens() is None


async def test_corrupt_keyring_record_does_not_expose_credential_in_error():
    import traceback

    import pytest

    from fusion_cli.core.errors import FusionError
    from fusion_cli.mcp_bridge.tokens import KeyringTokenStorage

    class CorruptKeyring:
        def get_password(self, service, account):
            return '{"access_token":"offline-fixture","token_type":{"private":"offline-fixture"}}'

    storage = KeyringTokenStorage("offline-fixture", backend=CorruptKeyring())
    with pytest.raises(FusionError) as caught:
        await storage.get_tokens()
    assert "offline-fixture" not in "".join(traceback.format_exception(caught.value))


async def test_independent_oauth_owners_share_same_storage_lease(tmp_path):
    """Ayrı backend sahipleri aynı anahtarlık namespace'inde yarışamaz."""
    first = OAuthFlowOwner(tmp_path).lock_for("offline-profile")
    second = OAuthFlowOwner(tmp_path).lock_for("offline-profile")
    entered = asyncio.Event()

    async def other_owner():
        async with second:
            entered.set()

    async with first:
        waiter = asyncio.create_task(other_owner())
        await asyncio.sleep(0)
        assert not entered.is_set()
    await waiter
    assert entered.is_set()


async def test_file_lease_excludes_other_real_process(tmp_path):
    import sys

    from fusion_cli.core.constants import MCP_NETWORK_TIMEOUT_S
    from fusion_cli.core.file_lease import FileLease

    path = tmp_path / "offline.lock"
    lease = FileLease(path)
    script = (
        "from pathlib import Path; from fusion_cli.core.file_lease import FileLease; "
        "import sys; lease=FileLease(Path(sys.argv[1])); "
        "print(lease.try_acquire()); lease.close()"
    )

    async def probe():
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(MCP_NETWORK_TIMEOUT_S):
                stdout, stderr = await process.communicate()
            assert process.returncode == 0, stderr.decode()
            return stdout.strip()
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    assert await asyncio.to_thread(lease.try_acquire)
    try:
        assert await probe() == b"False"
    finally:
        await asyncio.to_thread(lease.close)
    assert await probe() == b"True"

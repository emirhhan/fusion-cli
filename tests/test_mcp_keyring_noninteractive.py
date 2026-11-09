from __future__ import annotations

import asyncio
import threading
import traceback

import httpx
import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from fusion_cli.config.models import McpServerConfig, McpTransport
from fusion_cli.core.optional_read import OptionalReadWorker
from fusion_cli.mcp_bridge import oauth, pool, tokens
from fusion_cli.mcp_bridge.failures import McpFailureKind, classify_failure
from fusion_cli.mcp_bridge.oauth_flow import OAuthFlowOwner

from .test_mcp_oauth import MemoryKeyring


@pytest.mark.parametrize("status", [0, -25300, -25308, -25293])
def test_native_lookup_disallows_ui_and_distinguishes_missing_from_denied(status):
    import ctypes
    from types import SimpleNamespace

    from fusion_cli.mcp_bridge.keychain_read import KeychainReadUnavailableError, _copy_password

    queries, released = [], []

    def create_query(**values):
        queries.append(values)
        return values

    def copy(_query, result):
        if status == 0:
            ctypes.cast(result, ctypes.POINTER(ctypes.c_void_p)).contents.value = 1
        return status

    api = SimpleNamespace(
        create_query=create_query,
        k_=lambda name: name,
        SecItemCopyMatching=copy,
        cfstr_to_str=lambda _data: "fixture-password",
    )
    if status in {-25308, -25293}:
        with pytest.raises(KeychainReadUnavailableError):
            _copy_password("fixture-service", "fixture-account", api, released.append)
    else:
        assert _copy_password("fixture-service", "fixture-account", api, released.append) == (
            "fixture-password" if status == 0 else None
        )
    assert queries[0]["kSecUseAuthenticationUI"] == "kSecUseAuthenticationUIFail"
    assert queries[0]["kSecReturnData"] is True
    assert released


def remote():
    return McpServerConfig(
        name="fixture",
        transport=McpTransport.STREAMABLE_HTTP,
        url="https://offline.invalid/mcp",
        oauth_callback_port=12345,
    )


@pytest.mark.parametrize("ending", ["timeout", "cancel"])
async def test_blocked_noninteractive_read_is_bounded_without_queued_threads(monkeypatch, ending):
    entered, exited = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    calls = []

    class Blocking(MemoryKeyring):
        def get_password(self, service, account):
            calls.append(1)
            loop.call_soon_threadsafe(entered.set)
            try:
                release.wait(2)
                return None
            finally:
                loop.call_soon_threadsafe(exited.set)

    monkeypatch.setattr(
        tokens, "_token_reader", OptionalReadWorker("fixture-mcp-keyring"), raising=False
    )
    monkeypatch.setattr(tokens, "NONINTERACTIVE_READ_TIMEOUT_S", 0.03, raising=False)
    storage = tokens.KeyringTokenStorage("fixture", backend=Blocking(), interactive=False)
    task = asyncio.create_task(storage.get_tokens())
    try:
        await asyncio.wait_for(entered.wait(), 0.2)
        if ending == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 0.2)
        else:
            with pytest.raises(tokens.McpTokenStorageError):
                await asyncio.wait_for(task, 0.2)
        with pytest.raises(tokens.McpTokenStorageError):
            await asyncio.wait_for(storage.get_tokens(), 0.2)
        assert calls == [1]
        workers = [t for t in threading.enumerate() if t.name == "fixture-mcp-keyring"]
        assert len(workers) == 1 and workers[0].daemon
    finally:
        release.set()
    await asyncio.wait_for(exited.wait(), 0.2)


async def test_locked_read_is_login_required_never_missing_or_secret_error(monkeypatch):
    class Locked(MemoryKeyring):
        def get_password(self, *_args):
            raise RuntimeError("private-canary-do-not-log")

    storage = tokens.KeyringTokenStorage("fixture", backend=Locked(), interactive=False)
    with pytest.raises(tokens.McpTokenStorageError) as caught:
        await storage.get_tokens()
    failure = classify_failure(caught.value, remote())
    assert failure.kind is McpFailureKind.LOGIN_REQUIRED
    assert "private-canary" not in "".join(traceback.format_exception(caught.value))


async def test_missing_noninteractive_item_remains_missing():
    storage = tokens.KeyringTokenStorage("fixture", backend=MemoryKeyring(), interactive=False)
    assert await storage.get_tokens() is None


@pytest.mark.parametrize("count", [2, 3])
async def test_healthy_parallel_namespaces_wait_within_the_same_read_deadline(monkeypatch, count):
    import time

    class SlowHealthy(MemoryKeyring):
        def get_password(self, service, account):
            time.sleep(0.02)
            return OAuthToken(access_token="fixture", token_type="Bearer").model_dump_json()

    monkeypatch.setattr(tokens, "_token_reader", OptionalReadWorker("fixture-mcp-keyring"))
    stores = [
        tokens.KeyringTokenStorage(f"fixture-{i}", backend=SlowHealthy(), interactive=False)
        for i in range(count)
    ]
    result = await asyncio.gather(*(store.get_tokens() for store in stores))
    assert all(value is not None for value in result)


async def bundle(monkeypatch, *, interactive=False, failing=False):
    backend = MemoryKeyring()
    saved = tokens.KeyringTokenStorage(remote().url, backend=backend)
    await saved.set_client_info(
        OAuthClientInformationFull(
            client_id="fixture-client", redirect_uris=["http://localhost:11111/callback"]
        )
    )
    await saved.set_tokens(
        OAuthToken(
            access_token="fixture-access",
            refresh_token="fixture-refresh",
            token_type="Bearer",
            expires_in=3600,
        )
    )
    before = dict(backend.values)

    class Store(tokens.KeyringTokenStorage):
        async def get_client_info(self):
            if failing:
                raise tokens.McpTokenStorageError("Keychain unavailable")
            return await super().get_client_info()

    monkeypatch.setattr(
        oauth, "KeyringTokenStorage", lambda url, **kwargs: Store(url, backend=backend, **kwargs)
    )
    owner = OAuthFlowOwner()
    monkeypatch.setattr(pool, "mcp_oauth_flows", lambda: owner)
    return await oauth.oauth_provider_for(remote(), interactive=interactive), backend, before


async def test_valid_noninteractive_cache_is_not_cleared_for_new_callback(monkeypatch):
    auth, backend, before = await bundle(monkeypatch)
    flow = auth.auth.async_auth_flow(
        httpx.Request("POST", remote().url, json={"method": "initialize"})
    )
    try:
        outgoing = await anext(flow)
        assert outgoing.headers["authorization"] == "Bearer fixture-access"
        assert backend.values == before
    finally:
        await flow.aclose()
        await auth.callback.close()


async def test_unavailable_noninteractive_lookup_cannot_clear_cached_credentials(monkeypatch):
    from unittest.mock import AsyncMock

    clear = AsyncMock(side_effect=AssertionError("unavailable lookup must not clear"))
    monkeypatch.setattr(tokens.KeyringTokenStorage, "clear", clear)
    with pytest.raises(tokens.McpTokenStorageError):
        await bundle(monkeypatch, failing=True)
    clear.assert_not_called()


async def test_client_reports_keychain_unavailable_as_login_required(monkeypatch):
    from fusion_cli.mcp_bridge.client import McpClient

    async def unavailable(*_args, **_kwargs):
        raise tokens.McpTokenStorageError("Anahtarlık etkileşimsiz okunamadı.")

    monkeypatch.setattr(oauth, "oauth_provider_for", unavailable)
    async with McpClient((remote(),), timeout_seconds=0.2, interactive=False) as client:
        assert client.statuses["fixture"].kind == McpFailureKind.LOGIN_REQUIRED


def test_default_mac_noninteractive_backend_uses_no_ui_query(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    import keyring

    from fusion_cli.mcp_bridge import keychain_read

    native = Mock(return_value="fixture-only")
    forbidden = Mock(side_effect=AssertionError("interactive backend must not run"))
    monkeypatch.setattr(tokens, "sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr(keychain_read, "read_password_noninteractive", native)
    monkeypatch.setattr(keyring, "get_password", forbidden)
    assert (
        tokens._SystemKeyring(interactive=False).get_password("fixture", "account")
        == "fixture-only"
    )
    native.assert_called_once_with("fixture", "account")
    forbidden.assert_not_called()


async def test_explicit_interactive_login_retains_stale_registration_reset(monkeypatch):
    auth, backend, before = await bundle(monkeypatch, interactive=True)
    assert before and not backend.values
    await auth.callback.close()


async def test_noninteractive_valid_refresh_still_persists_under_owned_write(monkeypatch):
    real_provider = oauth.OAuthClientProvider

    def expired(*args, **kwargs):
        provider = real_provider(*args, **kwargs)
        provider.context.token_expiry_time = 1
        return provider

    monkeypatch.setattr(oauth, "OAuthClientProvider", expired)
    auth, backend, before = await bundle(monkeypatch)
    request = httpx.Request("POST", remote().url, json={"method": "initialize"})
    flow = auth.auth.async_auth_flow(request)
    try:
        refresh = await anext(flow)
        assert b"grant_type=refresh_token" in refresh.content
        outgoing = await flow.asend(
            httpx.Response(
                200,
                request=refresh,
                json={
                    "access_token": "fixture-new-access",
                    "refresh_token": "fixture-new-refresh",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        )
        assert (
            outgoing is request and outgoing.headers["authorization"] == "Bearer fixture-new-access"
        )
        assert backend.values != before
    finally:
        await flow.aclose()
        await auth.callback.close()

"""Web sağlayıcı seçilmeden Keychain erişimi API turunu durduramaz."""

from __future__ import annotations

from dataclasses import replace

import pytest
from cryptography.fernet import Fernet

from fusion_cli.config import keys
from fusion_cli.config.credentials import FernetSecretStore
from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.types import CompletionRequest, Message
from fusion_cli.providers import web_registry
from fusion_cli.providers.chain import FallbackProvider
from fusion_cli.providers.web_session import WebTurn

from .fakes import ScriptedProvider, make_config, model_result


def _config(session):
    return replace(make_config(), web_sessions=(session,))


def _browser(ref=""):
    return WebSessionConfig(
        model="browser-test", transport="browser", provider="chatgpt", credential_ref=ref
    )


def _request():
    return CompletionRequest(
        messages=(Message("user", "sentetik"),), temperature=0, max_tokens=16, timeout_s=1
    )


def test_unmatched_api_model_never_opens_credential_store(monkeypatch):
    def forbidden():
        pytest.fail("API modelinin registry hazırlığı Keychain erişimi başlattı")

    monkeypatch.setattr(keys, "secret_key", forbidden)
    registry = web_registry.web_registry_for(_config(_browser("cookie")))
    assert registry.build("api-only") is None


@pytest.mark.parametrize(
    "session",
    [
        WebSessionConfig(model="http-test", endpoint="https://synthetic.invalid", auth_env="TOKEN"),
        _browser(),
    ],
)
def test_http_and_credentialless_browser_never_open_keychain(session, monkeypatch):
    monkeypatch.setattr(keys, "secret_key", lambda: pytest.fail("Gereksiz Keychain erişimi"))
    monkeypatch.setattr(keys, "environ_snapshot", lambda: {"TOKEN": "synthetic-token"})
    registry = web_registry.web_registry_for(_config(session))
    credential = registry.credential_for(session)
    assert credential.token == ("synthetic-token" if session.transport == "http" else "")


@pytest.mark.asyncio
async def test_api_success_does_not_read_credentials_of_unused_web_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        keys, "secret_key", lambda: pytest.fail("Kullanılmayan yedek Keychain açtı")
    )
    monkeypatch.setattr(web_registry, "build_browser_transport", lambda *a, **k: _transport)
    registry = web_registry.web_registry_for(_config(_browser("cookie")))
    web = registry.build("browser-test")
    api = ScriptedProvider([model_result("api-ok")])
    result = await FallbackProvider([api, web], role="agent").complete(_request())
    assert result.text == "api-ok"


async def _transport(credential, messages, model):
    return WebTurn(credential.token)


@pytest.mark.asyncio
async def test_selected_web_reads_fresh_secret_on_use_and_refreshes_registry(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    key = Fernet.generate_key().decode()
    store = FernetSecretStore(path, secret_key=key)
    store.set("cookie", "first-cookie")
    reads = []
    monkeypatch.setattr(keys, "secret_key", lambda: reads.append(1) or key)
    monkeypatch.setattr(web_registry, "credentials_file", lambda: path)
    monkeypatch.setattr(web_registry, "build_browser_transport", lambda *a, **k: _transport)
    config = _config(_browser("cookie"))
    registry = web_registry.web_registry_for(config)
    provider = registry.build("browser-test")
    assert reads == []
    assert (await provider.complete(_request())).text == "first-cookie"
    store.set("cookie", "updated-cookie")
    assert (await provider.complete(_request())).text == "updated-cookie"
    assert reads == [1]
    refreshed = web_registry.web_registry_for(config).build("browser-test")
    assert (await refreshed.complete(_request())).text == "updated-cookie"
    assert reads == [1, 1]


def test_credential_factory_exception_is_not_memoized(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode()
    path = tmp_path / "credentials.json"
    FernetSecretStore(path, secret_key=key).set("cookie", "retry-cookie")
    calls = []

    def unlock():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("sentetik erişim hatası")
        return key

    monkeypatch.setattr(keys, "secret_key", unlock)
    monkeypatch.setattr(web_registry, "credentials_file", lambda: path)
    session = _browser("cookie")
    registry = web_registry.web_registry_for(_config(session))
    with pytest.raises(RuntimeError):
        registry.credential_for(session)
    assert registry.credential_for(session).token == "retry-cookie"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_web_fallback_reads_store_only_when_primary_fails(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    key = Fernet.generate_key().decode()
    FernetSecretStore(path, secret_key=key).set("cookie", "fallback-cookie")
    reads = []
    monkeypatch.setattr(keys, "secret_key", lambda: reads.append(1) or key)
    monkeypatch.setattr(web_registry, "credentials_file", lambda: path)
    monkeypatch.setattr(web_registry, "build_browser_transport", lambda *a, **k: _transport)
    registry = web_registry.web_registry_for(_config(_browser("cookie")))
    web = registry.build("browser-test")
    assert reads == []
    api = ScriptedProvider([model_result(ok=False, error="temporary unavailable")])
    result = await FallbackProvider([api, web], role="agent").complete(_request())
    assert result.text == "fallback-cookie"
    assert reads == [1]


def test_injected_store_wins_over_factory(tmp_path):
    store = FernetSecretStore(
        tmp_path / "credentials.json", secret_key=Fernet.generate_key().decode()
    )
    store.set("cookie", "injected-cookie")
    registry = web_registry.WebSessionRegistry(
        (_browser("cookie"),),
        environ={},
        secret_store=store,
        secret_store_factory=lambda: pytest.fail("Verilmiş depo varken factory çağrıldı"),
    )
    assert registry.credential_for(_browser("cookie")).token == "injected-cookie"


def test_registry_refresh_uses_rotated_master_key_without_global_cache(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    active_key = [Fernet.generate_key().decode()]
    FernetSecretStore(path, secret_key=active_key[0]).set("cookie", "old-cookie")
    monkeypatch.setattr(keys, "secret_key", lambda: active_key[0])
    monkeypatch.setattr(web_registry, "credentials_file", lambda: path)
    session = _browser("cookie")
    config = _config(session)
    first = web_registry.web_registry_for(config)
    assert first.credential_for(session).token == "old-cookie"
    # Yalnız tmp_path içindeki sentetik kasa: kullanıcı master-key rotasyonunu temsil eder.
    path.unlink()
    active_key[0] = Fernet.generate_key().decode()
    FernetSecretStore(path, secret_key=active_key[0]).set("cookie", "rotated-cookie")
    refreshed = web_registry.web_registry_for(config)
    assert refreshed.credential_for(session).token == "rotated-cookie"

"""WebSessionRegistry — config + env'den model kimliği için web sağlayıcı çözer."""

from __future__ import annotations

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.providers.web_registry import WebSessionRegistry


async def _fake_transport(credential, messages, model):
    return f"cevap[{model}]"


def _factory(endpoint, **_):
    """Sahte transport üreticisi: gerçek ağ yerine sabit cevap."""
    return _fake_transport


def test_eslesmeyen_model_none_doner():
    reg = WebSessionRegistry((), environ={})

    assert reg.build("herhangi/model", transport_factory=_factory) is None


def test_eslesen_model_icin_web_adaptor_kurulur():
    sessions = (
        WebSessionConfig(model="benim-uc", endpoint="http://localhost/v1", auth_env="MY_TOKEN"),
    )
    reg = WebSessionRegistry(sessions, environ={"MY_TOKEN": "sir-token"})

    provider = reg.build("benim-uc", transport_factory=_factory)

    assert provider is not None
    assert provider.label == "benim-uc"


async def test_token_env_degiskeninden_okunur():
    sessions = (WebSessionConfig(model="uc", endpoint="http://x/v1", auth_env="TOK"),)
    captured: dict = {}

    def _capturing_factory(endpoint, **_):
        async def _t(credential, messages, model):
            captured["token"] = credential.token
            return "ok"

        return _t

    reg = WebSessionRegistry(sessions, environ={"TOK": "gizli"})
    provider = reg.build("uc", transport_factory=_capturing_factory)
    assert provider is not None

    from fusion_cli.core.types import CompletionRequest, Message

    request = CompletionRequest(
        messages=(Message("user", "selam"),), temperature=0.0, max_tokens=100, timeout_s=10.0
    )
    await provider.complete(request)

    assert captured["token"] == "gizli"


def test_auth_env_yoksa_token_bos_kalir():
    sessions = (WebSessionConfig(model="uc", endpoint="http://x/v1", auth_env=None),)
    reg = WebSessionRegistry(sessions, environ={})

    provider = reg.build("uc", transport_factory=_factory)

    assert provider is not None  # cookie/başlıksız da kurulur (kullanıcının kendi ucu)


def test_tool_support_stringi_enuma_cevrilir():
    sessions = (WebSessionConfig(model="uc", endpoint="http://x/v1", tool_support="emulated"),)
    reg = WebSessionRegistry(sessions, environ={})

    provider = reg.build("uc", transport_factory=_factory)

    assert provider is not None
    assert provider._tool_support is ToolSupport.EMULATED

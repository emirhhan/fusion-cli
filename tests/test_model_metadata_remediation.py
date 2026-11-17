"""Model kimliğine bağlı yeteneğin seçim ve yedekte korunması."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from fusion_cli.config.model_select import apply_single_model
from fusion_cli.core.types import ModelSpec
from fusion_cli.providers.factory import build_provider

from .fakes import make_config, request


def test_single_model_reselection_preserves_identity_metadata():
    config = make_config()
    primary = ModelSpec(
        name="agent",
        model="test/primary",
        tags=("agent", "reasoning", "vision"),
        supported_reasoning_efforts=("high",),
        reasoning_efforts_verified=True,
    )
    config = replace(config, agent=primary)
    selected = apply_single_model(config, "test/primary").agent
    assert selected.supported_reasoning_efforts == ("high",)
    assert selected.reasoning_efforts_verified
    assert {"agent", "reasoning", "vision", "strict"} <= set(selected.tags)


def test_single_model_change_resolves_new_identity_only():
    config = make_config()
    candidate = ModelSpec(
        name="candidate",
        model="test/new",
        tags=("reasoning",),
        supported_reasoning_efforts=("medium",),
        reasoning_efforts_verified=True,
    )
    config = replace(config, candidates=(candidate,))
    selected = apply_single_model(config, "test/new").agent
    assert selected.supported_reasoning_efforts == ("medium",)
    assert selected.reasoning_efforts_verified
    unknown = apply_single_model(config, "test/unknown").agent
    assert not unknown.reasoning_efforts_verified
    assert unknown.tags == ("strict",)


async def test_fallback_uses_its_own_verified_effort_record(monkeypatch):
    captured = []

    async def complete(**kwargs):
        captured.append(kwargs)
        if kwargs["model"] == "test/primary":
            raise ValueError("sahte sağlayıcı reddi")
        return SimpleNamespace(
            model="test/fallback",
            usage=None,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Yanıt", tool_calls=None), finish_reason="stop"
                )
            ],
        )

    monkeypatch.setattr("fusion_cli.providers.factory.configure_litellm", lambda: None)
    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=complete),
    )
    primary = ModelSpec(name="agent", model="test/primary", fallback=("test/fallback",))
    fallback = ModelSpec(
        name="other",
        model="test/fallback",
        supported_reasoning_efforts=("high",),
        reasoning_efforts_verified=True,
    )
    provider = build_provider(primary, publisher=None, retry_delays_s=(), model_specs=(fallback,))
    result = await provider.complete(request(reasoning_effort="high"))
    assert result.ok
    assert "reasoning_effort" not in captured[0]
    assert captured[1]["reasoning_effort"] == "high"
    assert result.applied_effort == "high"


async def test_side_chat_factory_connects_configured_fallback_proof(monkeypatch):
    from fusion_cli.appserver.side_chat import _default_provider

    captured = []

    async def complete(**kwargs):
        captured.append(kwargs)
        if kwargs["model"] == "test/primary":
            raise ValueError("sahte sağlayıcı reddi")
        return SimpleNamespace(
            model="test/fallback",
            usage=None,
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Yanıt", tool_calls=None), finish_reason="stop"
                )
            ],
        )

    monkeypatch.setattr("fusion_cli.providers.factory.configure_litellm", lambda: None)
    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=complete),
    )
    primary = ModelSpec(name="agent", model="test/primary", fallback=("test/fallback",))
    fallback = ModelSpec(
        name="other",
        model="test/fallback",
        supported_reasoning_efforts=("high",),
        reasoning_efforts_verified=True,
    )
    config = make_config(agent=primary, candidates=(fallback,))
    provider = _default_provider(config)
    result = await provider.complete(request(reasoning_effort="high"))
    assert result.ok
    assert captured[-1]["reasoning_effort"] == "high"
    assert result.applied_effort == "high"

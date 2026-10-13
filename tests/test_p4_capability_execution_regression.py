"""P4: exact, model-scoped reasoning and provider-observed identity contracts."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.config.eligibility import capability_from_spec
from fusion_cli.core.reasoning import resolve_reasoning
from fusion_cli.core.types import CompletionRequest, ModelSpec
from fusion_cli.providers.litellm_provider import LiteLlmProvider


def _request(effort: str | None = "high") -> CompletionRequest:
    return CompletionRequest(
        messages=(), temperature=0.0, max_tokens=128,
        timeout_s=10.0, reasoning_effort=effort,
    )


def test_model_identity_change_invalidates_capability_evidence() -> None:
    original = ModelSpec(
        name="agent", model="provider/A",
        supported_reasoning_efforts=("high",), reasoning_efforts_verified=True,
    )
    assert original.with_identity("provider/A") is original
    other = original.with_identity("provider/B")
    assert other.model == "provider/B"
    assert not other.reasoning_efforts_verified
    assert other.supported_reasoning_efforts == ()
    assert resolve_reasoning("high", capability_from_spec(other)).applied is None
    assert resolve_reasoning("high", capability_from_spec(original)).applied == "high"


def test_native_kwargs_are_not_sent_without_verification() -> None:
    provider = LiteLlmProvider("provider/unknown", role="agent")
    assert "reasoning_effort" not in provider._call_kwargs(_request(), stream=False)


def test_native_kwargs_use_verified_exact_level() -> None:
    from fusion_cli.core.model_capability import ModelCapability

    capability = ModelCapability(
        supported_reasoning_efforts=("high",),
        reasoning_efforts_verified=True,
    )
    provider = LiteLlmProvider("provider/A", role="agent", capability=capability)
    assert provider._call_kwargs(_request("high"), stream=False)["reasoning_effort"] == "high"
    assert provider._call_kwargs(_request("max"), stream=False)["reasoning_effort"] == "high"
    assert "reasoning_effort" not in provider._call_kwargs(_request("low"), stream=False)


@pytest.mark.asyncio
async def test_observed_model_and_effort_receipts_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fusion_cli.core.model_capability import ModelCapability

    captured: dict[str, object] = {}
    async def completion(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            model="provider/actually-served",
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
                finish_reason="stop",
            )],
            usage=None,
        )
    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=completion),
    )
    provider = LiteLlmProvider(
        "provider/requested", role="agent",
        capability=ModelCapability(
            supported_reasoning_efforts=("high",),
            reasoning_efforts_verified=True,
        ),
    )
    result = await provider.complete(_request("max"))
    assert captured["reasoning_effort"] == "high"
    assert result.model == "provider/requested"
    assert result.served_by == "provider/actually-served"
    assert result.requested_effort == "max"
    assert result.applied_effort == "high"
    assert result.effort_reason

"""Model çalıştırma makbuzu ve doğrulanmamış effort için çevrimdışı sözleşme."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.providers.litellm_provider import LiteLlmProvider

from .fakes import request


@pytest.mark.parametrize("observed", ["gercek/surum", None])
async def test_response_model_is_observed_without_inventing_missing_evidence(
    monkeypatch: pytest.MonkeyPatch, observed: str | None
) -> None:
    """İstenen model sabit kalır; gerçek yanıt kimliği ayrı taşınır."""
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="Yanıt", tool_calls=None), finish_reason="stop"
            )
        ],
        usage=None,
    )
    if observed is not None:
        response.model = observed

    async def complete(**kwargs: object) -> SimpleNamespace:
        return response

    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=complete),
    )
    result = await LiteLlmProvider("istenen/model", role="agent").complete(request())
    assert result.ok
    assert result.model == "istenen/model"
    assert result.served_by == (observed or "")


async def test_unknown_model_does_not_send_unverified_native_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bilinmeyen modelde ham effort SDK'nın sessiz düşürmesine bırakılmaz."""
    captured: dict[str, object] = {}

    async def complete(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Yanıt", tool_calls=None), finish_reason="stop"
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=complete),
    )
    result = await LiteLlmProvider("bilinmeyen/model", role="agent").complete(
        request(reasoning_effort="high")
    )
    assert result.ok
    assert "reasoning_effort" not in captured


async def test_supported_effort_has_truthful_execution_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fusion_cli.core.model_capability import ModelCapability

    captured: dict[str, object] = {}

    async def complete(**kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Yanıt", tool_calls=None), finish_reason="stop"
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=complete),
    )
    provider = LiteLlmProvider(
        "istenen/model",
        role="agent",
        capability=ModelCapability(
            supported_reasoning_efforts=("high",), reasoning_efforts_verified=True
        ),
    )
    result = await provider.complete(request(reasoning_effort="max"))
    assert captured["reasoning_effort"] == "high"
    assert result.requested_effort == "max"
    assert result.applied_effort == "high"
    assert result.effort_reason


@pytest.mark.parametrize("rebuild_fails", [True, False])
async def test_stream_retains_chunk_observed_model_when_builder_loses_metadata(
    monkeypatch: pytest.MonkeyPatch, rebuild_fails: bool
) -> None:
    from fusion_cli.core.types import StreamDone

    chunk = SimpleNamespace(
        model="gercek/model", choices=[SimpleNamespace(delta=SimpleNamespace(content="Yanıt"))]
    )

    async def chunks():
        yield chunk

    async def complete(**kwargs: object):
        return chunks()

    def rebuild(*args: object, **kwargs: object):
        if rebuild_fails:
            raise ValueError("sahte builder hatası")
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Yanıt", tool_calls=None), finish_reason="stop"
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=complete, stream_chunk_builder=rebuild),
    )
    items = [
        item async for item in LiteLlmProvider("istenen/model", role="agent").stream(request())
    ]
    done = items[-1]
    assert isinstance(done, StreamDone)
    assert done.result.model == "istenen/model"
    assert done.result.served_by == "gercek/model"


async def test_factory_and_fallback_do_not_share_primary_effort_proof(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.providers.factory import build_provider

    captured: list[dict[str, object]] = []

    async def complete(**kwargs: object) -> SimpleNamespace:
        captured.append(kwargs)
        if kwargs["model"] == "openrouter/primary":
            raise ValueError("sahte sağlayıcı reddi")
        return SimpleNamespace(
            model="actual/fallback",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="Yanıt", tool_calls=None), finish_reason="stop"
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=complete),
    )
    spec = ModelSpec(
        name="agent",
        model="openrouter/primary",
        fallback=("openrouter/fallback",),
        supported_reasoning_efforts=("high",),
        reasoning_efforts_verified=True,
    )
    provider = build_provider(spec, publisher=None, retry_delays_s=())
    result = await provider.complete(request(reasoning_effort="high"))
    assert captured[0]["reasoning_effort"] == "high"
    assert "reasoning_effort" not in captured[1]
    assert result.model == "openrouter/fallback"
    assert result.served_by == "actual/fallback"
    assert result.requested_effort == "high"
    assert result.applied_effort is None
    assert result.effort_reason

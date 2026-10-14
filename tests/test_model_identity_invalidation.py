"""Kimlik değişikliği eski modelin doğrulanmış yoğunluğunu yeni uca taşımaz."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fusion_cli.config import model_select
from fusion_cli.core.types import ModelSpec
from fusion_cli.providers.factory import build_provider

from .fakes import make_config, request


@pytest.mark.parametrize("role", ["agent", "judge", "candidate", "escalation"])
async def test_public_model_changes_invalidate_old_effort_before_factory_boundary(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = ModelSpec(
        name="a",
        model="openrouter/A",
        fallback=("openrouter/B",),
        supported_reasoning_efforts=("high",),
        reasoning_efforts_verified=True,
    )
    config = make_config(agent=spec, judge=spec, candidates=(spec,), task_model_map={"code": "a"})
    if role == "agent":
        changed = model_select.set_agent_model(config, "openrouter/B").agent
    elif role == "judge":
        changed = model_select.set_judge_model(config, "openrouter/B").judge
    elif role == "candidate":
        changed = model_select.set_candidate_model(config, "a", "openrouter/B").candidates[0]
    else:
        changed = model_select.escalated_spec(spec, 1)
    captured: list[dict[str, object]] = []

    async def complete(**kwargs: object):
        captured.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="yanıt", tool_calls=None), finish_reason="stop"
                )
            ],
            usage=None,
        )

    monkeypatch.setattr(
        "fusion_cli.providers.litellm_provider._litellm",
        lambda: SimpleNamespace(acompletion=complete),
    )
    await build_provider(changed, publisher=None, retry_delays_s=()).complete(
        request(reasoning_effort="high")
    )
    assert "reasoning_effort" not in captured[0]
    assert not changed.reasoning_efforts_verified
    assert changed.supported_reasoning_efforts == ()


def test_reselecting_same_identity_preserves_its_own_evidence() -> None:
    spec = ModelSpec(
        name="a",
        model="openrouter/A",
        supported_reasoning_efforts=("high",),
        reasoning_efforts_verified=True,
    )
    config = make_config(agent=spec)
    assert model_select.set_agent_model(config, "openrouter/A").agent == spec

"""Denetçi şeması taşımada uygulanır; ana aktör isteği değişmez."""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.core.types import CompletionRequest, Message
from fusion_cli.providers.litellm_provider import LiteLlmProvider


def test_explicit_response_schema_reaches_sdk_format_without_actor_default():
    request = CompletionRequest((Message("user", "Return JSON."),), 0, 8192, 600)
    provider = LiteLlmProvider("nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b", role="hakem")
    schema = {"type": "object", "properties": {"value": {"type": "string"}}}
    kwargs = provider._call_kwargs(replace(request, response_schema=schema), stream=False)
    assert kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "fusion_response", "strict": True, "schema": schema},
    }
    assert "response_format" not in provider._call_kwargs(request, stream=False)
    assert kwargs["max_tokens"] == 8192
    assert kwargs["timeout"] == 600
    assert kwargs["num_retries"] == 0


def test_nim_budgeted_utility_reasoning_is_explicit_bounded_and_reported():
    from .fakes import model_result

    request = CompletionRequest(
        (Message("user", "Return JSON."),),
        0,
        8192,
        600,
        reasoning_effort="medium",
        reasoning_budget=1024,
    )
    provider = LiteLlmProvider("nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b", role="hakem")
    kwargs = provider._call_kwargs(request, stream=False)
    assert kwargs["extra_body"] == {"reasoning_effort": "medium", "reasoning_budget": 1024}
    assert "reasoning_effort" not in kwargs  # SDK bu alanı düşürdüğü için yerel gövdede taşınır.
    receipt = provider._with_effort(model_result("{}"), request)
    assert receipt.requested_effort == receipt.applied_effort == "medium"


async def test_required_nim_grounding_requests_schema_but_generic_review_does_not(
    monkeypatch, tmp_path
):
    from fusion_cli.config.model_select import apply_single_model
    from fusion_cli.engines.agent import research_grounding as grounding

    from .fakes import RecordingSink, model_result
    from .test_agent_loop import _deps
    from .test_research_grounding import target_sources, typed_clean

    _, target, sources = target_sources(tmp_path)
    deps = _deps(tmp_path, RecordingSink(), runtime={"max_tokens": 8192})
    deps.config = apply_single_model(deps.config, "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b")
    requests = []

    class Provider:
        async def complete(self, request):
            requests.append(request)
            prompt = request.messages[0].content
            return model_result(typed_clean(prompt) if "\nDATA\n" in prompt else "TAMAM")

    monkeypatch.setattr(grounding.review, "build_provider", lambda *args, **kwargs: Provider())
    verdict = await grounding.review_grounding(target, sources, deps)
    await grounding.review._ask("Optional generic review.", deps.config, deps.publisher)
    assert verdict.status == "supported"
    assert requests[0].response_schema is not None
    assert not requests[0].disable_thinking
    assert requests[0].reasoning_budget == 1024
    assert requests[0].reasoning_effort == "medium"
    assert requests[1].response_schema is None
    assert not requests[1].disable_thinking

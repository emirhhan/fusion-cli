"""Exact main-model effort receipt through installed SDK; all HTTP mocked, sockets forbidden."""

# Imports below the guards must not trigger SDK side effects before isolation.
# ruff: noqa: E402
import asyncio
import dataclasses
import json
import os
import socket
import sys

assert os.environ["LITELLM_MODE"] == "PRODUCTION"
assert os.environ["PYTHON_DOTENV_DISABLED"] == "1"
blocked = []


def forbid(*args, **kwargs):
    blocked.append("blocked socket/DNS attempt")
    raise AssertionError("Network forbidden")


socket.create_connection = forbid
socket.getaddrinfo = forbid
socket.socket.connect = forbid
socket.socket.connect_ex = forbid
import httpx
import litellm

from fusion_cli.config.eligibility import capability_from_spec, effort_for_spec
from fusion_cli.core.reasoning import ReasoningEffort, resolve_reasoning
from fusion_cli.core.types import CompletionRequest, Message, ModelSpec, StreamDone
from fusion_cli.providers.litellm_provider import LiteLlmProvider, configure_litellm

assert "fusion_cli.config.loader" not in sys.modules
litellm.telemetry = False
litellm.set_verbose = False
configure_litellm()
active = None


async def send(self, request, **kwargs):
    assert active is not None and request.url.host == "nim-fixture.invalid"
    return await active.handle_async_request(request)


httpx.AsyncClient.send = send
MODEL = "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"


async def case(name, effort, verified, disable, stream):
    global active
    bodies = []
    spec = ModelSpec(
        name="synthetic-main",
        model=MODEL,
        tags=("agent", "reasoning"),
        supported_reasoning_efforts=("low", "medium", "high") if verified else (),
        reasoning_efforts_verified=verified,
    )
    cap = capability_from_spec(spec)
    requested = effort_for_spec(spec, ReasoningEffort(effort))
    req = CompletionRequest(
        messages=(Message("user", "synthetic offline fixture"),),
        temperature=0,
        max_tokens=16,
        timeout_s=2,
        max_retries=0,
        reasoning_effort=requested,
        disable_thinking=disable,
    )
    provider = LiteLlmProvider(
        MODEL, role="main-offline", capability=cap, api_key="synthetic-not-a-real-key"
    )
    leaf = provider._call_kwargs(req, stream=stream)

    def handle(request):
        body = json.loads(request.content)
        assert body["model"] == MODEL.removeprefix("nvidia_nim/")
        bodies.append(body)
        common = {"id": "fixture", "created": 1, "model": body["model"]}
        if not stream:
            return httpx.Response(
                200,
                request=request,
                json={
                    **common,
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
        chunk = {
            **common,
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}],
        }
        final = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/event-stream"},
            content="data: "
            + json.dumps(chunk)
            + "\n\ndata: "
            + json.dumps(final)
            + "\n\ndata: [DONE]\n\n",
        )

    active = httpx.MockTransport(handle)
    result = None
    async with asyncio.timeout(20):
        if stream:
            async for item in provider.stream(req):
                if isinstance(item, StreamDone):
                    result = item.result
        else:
            result = await provider.complete(req)
    assert result is not None and result.ok and result.text == "ok"
    assert len(bodies) == 1
    return {
        "name": name,
        "configured_effort_fixture": effort,
        "mode": "stream" if stream else "complete",
        "capability_fixture": {
            "reasoning": cap.reasoning,
            "supported_reasoning_efforts": cap.supported_reasoning_efforts,
            "reasoning_efforts_verified": cap.reasoning_efforts_verified,
        },
        "request_reasoning_effort": requested,
        "request_disable_thinking": disable,
        "resolution": dataclasses.asdict(resolve_reasoning(requested, cap)),
        "leaf_kwargs": {
            k: leaf[k]
            for k in ("model", "reasoning_effort", "extra_body", "allowed_openai_params", "stream")
            if k in leaf
        },
        "wire_bodies": bodies,
        "metadata": {
            "requested_effort": result.requested_effort,
            "applied_effort": result.applied_effort,
            "effort_reason": result.effort_reason,
            "ok": result.ok,
        },
    }


async def main():
    effort, mode, disable = sys.argv[1:]
    receipt = await case("fixture", effort, True, disable == "1", mode == "stream")
    assert "fusion_cli.config.loader" not in sys.modules
    assert not blocked
    print(json.dumps(receipt, ensure_ascii=False))


asyncio.run(main())

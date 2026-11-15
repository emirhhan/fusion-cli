"""Isolated installed SDK/Fusion leaf test. All HTTP is MockTransport; sockets forbidden."""

# Imports below the guards must not trigger SDK side effects before isolation.
# ruff: noqa: E402

import asyncio
import json
import os
import socket
import sys

# LiteLLM DEV imports can discover .env above the entrypoint; disable that path.
os.environ["LITELLM_MODE"] = "PRODUCTION"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"


# Installed before importing any application/provider package.
def forbid_network(*args, **kwargs):
    raise AssertionError("External network forbidden in offline fixture")


socket.create_connection = forbid_network
socket.getaddrinfo = forbid_network
socket.socket.connect = forbid_network
socket.socket.connect_ex = forbid_network

import httpx
import litellm

from fusion_cli.core.types import CompletionRequest, Message, StreamDone
from fusion_cli.providers.litellm_provider import LiteLlmProvider

litellm.suppress_debug_info = True
litellm.drop_params = True
litellm.telemetry = False
litellm.set_verbose = False
active = None


async def mocked_send(self, request, **kwargs):
    assert active is not None
    assert request.url.host == "nim-fixture.invalid"
    return await active.handle_async_request(request)


# Transport boundary only; actual LiteLLM dispatch, NIM mapping, SDK retry,
# Fusion leaf construction and stream processing remain installed code.
httpx.AsyncClient.send = mocked_send


async def run_case(requested_retries, stream):
    global active
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(
            {
                "stream": body.get("stream"),
                "max_retries_in_body": "max_retries" in body,
                "max_tokens": body.get("max_tokens"),
            }
        )
        if len(seen) <= 2:
            return httpx.Response(
                500,
                request=request,
                json={"error": {"message": "synthetic server error", "type": "server_error"}},
            )
        data = {
            "id": "fixture",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "nvidia/nemotron-3-ultra-550b-a55b",
            "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}],
        }
        final = {**data, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
        if not stream:
            data["object"] = "chat.completion"
            data["choices"] = [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ]
            return httpx.Response(200, request=request, json=data)
        payload = (
            "data: " + json.dumps(data) + "\n\ndata: " + json.dumps(final) + "\n\ndata: [DONE]\n\n"
        )
        return httpx.Response(
            200, request=request, headers={"content-type": "text/event-stream"}, content=payload
        )

    active = httpx.MockTransport(handler)
    provider = LiteLlmProvider(
        "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b",
        role="offline",
        api_key="synthetic-not-a-real-key",
    )
    req = CompletionRequest(
        messages=(Message("user", "fixture"),),
        temperature=0,
        max_tokens=16,
        timeout_s=2,
        max_retries=requested_retries,
    )
    result = None
    async with asyncio.timeout(20):
        if stream:
            async for item in provider.stream(req):
                if isinstance(item, StreamDone):
                    result = item.result
        else:
            result = await provider.complete(req)
    return {
        "requested_retries": requested_retries,
        "http_requests": len(seen),
        "ok": result.ok if result else None,
        "error_type": (result.error or "").split(":", 1)[0] if result else None,
        "requests": seen,
        "text": result.text if result else None,
    }


async def main():
    result = await run_case(int(sys.argv[1]), sys.argv[2] == "stream")
    print(json.dumps(result))


asyncio.run(main())

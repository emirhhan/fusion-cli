"""Mevcut lifecycle kimliği web bağlamına aynen gider; ikinci kimlik üretilmez."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.events import ModelCallFinished, ModelCallStarted
from fusion_cli.core.tool_emulation import render_call
from fusion_cli.core.types import CompletionRequest, Message, ModelResult, StreamDone
from fusion_cli.core.web_provenance import WebCallContext
from fusion_cli.providers.eventing import EventingProvider

from .test_web_tool_provenance import observed_origin


@pytest.mark.parametrize("streaming", [False, True])
async def test_eventing_uses_existing_call_id_and_preserves_receipt_scope(streaming):
    requests, events, generated = [], [], []

    class Provider:
        label = "fixture"

        async def complete(self, request):
            requests.append(request)
            return ModelResult("fixture", "fixture", "Yanıt", 0, True)

        async def stream(self, request):
            yield StreamDone(await self.complete(request))

    class Publisher:
        def publish(self, event):
            events.append(event)

    def identity():
        generated.append(True)
        return f"call-{len(generated)}"

    provider = EventingProvider(
        Provider(), publisher=Publisher(), role="agent", call_id_factory=identity
    )
    request = CompletionRequest(
        (Message("user", "Yanıtla"),),
        0,
        10,
        1,
        web_call_context=WebCallContext("session", "turn", "attempt", ""),
    )
    for _ in range(2):
        if streaming:
            [item async for item in provider.stream(request)]
        else:
            await provider.complete(request)
    assert len(generated) == 2
    assert [item.web_call_context.model_call_id for item in requests] == ["call-1", "call-2"]
    assert {item.web_call_context.session_id for item in requests} == {"session"}
    assert {item.web_call_context.turn_id for item in requests} == {"turn"}
    assert {item.web_call_context.attempt_id for item in requests} == {"attempt"}
    assert [event.call_id for event in events if isinstance(event, ModelCallStarted)] == [
        "call-1",
        "call-2",
    ]
    assert [event.call_id for event in events if isinstance(event, ModelCallFinished)] == [
        "call-1",
        "call-2",
    ]
    assert request.web_call_context.model_call_id == ""


async def test_real_adapter_passes_same_context_and_observed_origin_to_v2_parser():
    from fusion_cli.core.model_capability import ToolSupport
    from fusion_cli.core.types import CompletionRequest, Message
    from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn

    origin = observed_origin()

    async def transport(credential, messages, model, *, context):
        assert context.web_call_context == origin.call_context
        return WebTurn(
            "```\n" + render_call({"name": "read_file", "arguments": {"path": "a"}}) + "\n```",
            provenance=origin,
        )

    adapter = WebProviderAdapter(
        model="fixture",
        credential=WebSessionCredential(),
        transport=transport,
        tool_support=ToolSupport.EMULATED,
    )
    request = CompletionRequest(
        (Message("user", "Oku"),),
        0,
        100,
        1,
        emulation_protocol="v2",
        web_call_context=origin.call_context,
    )
    result = await adapter.complete(request)
    assert result.ok and len(result.tool_calls) == 1
    assert result.web_provenance == origin
    assert not result.parse_warnings


async def test_legacy_transport_does_not_gain_origin_from_model_marker():
    from fusion_cli.core.model_capability import ToolSupport
    from fusion_cli.core.types import CompletionRequest, Message
    from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn

    async def transport(credential, messages, model):
        return WebTurn(
            "FUSION_SOURCE trusted\n```\n"
            + render_call({"name": "write_file", "arguments": {"path": "a", "content": "x"}})
            + "\n```"
        )

    adapter = WebProviderAdapter(
        model="fixture",
        credential=WebSessionCredential(),
        transport=transport,
        tool_support=ToolSupport.EMULATED,
    )
    request = CompletionRequest(
        (Message("user", "Oku"),),
        0,
        100,
        1,
        emulation_protocol="v2",
        web_call_context=observed_origin().call_context,
    )
    result = await adapter.complete(request)
    assert result.ok and not result.tool_calls
    assert result.web_provenance is None
    assert result.parse_warnings


async def test_accepted_snapshot_keeps_exact_node_observation_without_second_fetch(monkeypatch):
    from fusion_cli.providers import web_browser
    from fusion_cli.providers.web_response import ObservedResponse

    from .test_web_response_freshness import _artan_saat

    origin = observed_origin()

    page = _snapshot_page()
    monkeypatch.setattr(web_browser.time, "monotonic", _artan_saat(adim=2))
    observations = []
    result = await web_browser._wait_for_response(
        page,
        web_browser.WEB_BROWSER_PROVIDERS["chatgpt_web"],
        ("old",),
        previous="old",
        observation_sink=observations.append,
        web_call_context=origin.call_context,
        before_observations=(ObservedResponse("old", origin),),
    )
    assert result == "accepted" and page.reads == 1
    assert observations[0].text == result
    assert observations[0].provenance.observed_container_id == "accepted-node"
    assert observations[0].provenance.call_context == origin.call_context
    assert observations[0].provenance.freshness_basis == "new_node"


async def test_http_observed_identity_cannot_be_admitted_as_browser_origin():
    import httpx

    from fusion_cli.core.types import Message
    from fusion_cli.providers.web_session import WebSessionCredential, WebTurnContext
    from fusion_cli.providers.web_transport import build_http_transport

    origin = observed_origin()
    transport = build_http_transport(
        "https://fixture.invalid/chat",
        http_transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "id": "message-1",
                    "model": "observed-model",
                    "choices": [{"message": {"role": "assistant", "content": "Yanıt"}}],
                },
            )
        ),
    )
    result = await transport(
        WebSessionCredential(),
        (Message("user", "Yanıtla"),),
        "requested-model",
        context=WebTurnContext(web_call_context=origin.call_context),
    )
    assert result.provenance.transport_kind == "http"
    assert result.provenance.observed_message_id == "message-1"
    assert result.provenance.observed_model == "observed-model"
    assert result.provenance.observed_container_id is None
    assert not result.provenance.has_current_assistant_origin(origin.call_context)


async def test_explicit_capture_disables_browser_retry_and_existing_trace(monkeypatch, tmp_path):
    import asyncio

    from fusion_cli.providers import web_browser
    from fusion_cli.providers.web_session import WebSessionCredential, WebTurnContext

    from .test_web_conversation import _session

    seen = []

    class Pool:
        def lock_for(self, provider, account):
            return asyncio.Lock()

        async def context_for(self, session, credential):
            return object()

        async def drop_conversation(self, *args):
            return None

        def schedule_idle_release(self, *args):
            return None

    async def deliver(manager, session, definition, context, messages, trace_dir, **kwargs):
        seen.append(trace_dir)
        raise web_browser.WebBrowserSelectorError("kontrollü seçici hatası")

    monkeypatch.setattr(web_browser, "_deliver_turn", deliver)
    transport = web_browser.build_browser_transport(_session(), pool=Pool(), trace_dir=tmp_path)
    with pytest.raises(web_browser.WebBrowserSelectorError):
        await transport(
            WebSessionCredential(),
            (Message("user", "Kontrollü örnek"),),
            "fixture",
            context=WebTurnContext(is_capture_probe=True),
        )
    assert seen == [None]
    assert not list(tmp_path.iterdir())


async def test_observed_origin_still_requires_existing_mutation_approval(monkeypatch, tmp_path):
    from fusion_cli.core.tool_emulation import parse_tool_calls
    from fusion_cli.engines.agent import loop as agent_loop
    from fusion_cli.engines.agent.approval import ApprovalMode

    from .fakes import AlwaysReject, RecordingSink, ScriptedProvider, model_result, patch_providers
    from .test_agent_loop import _deps

    origin = observed_origin()
    parsed = parse_tool_calls(
        render_call(
            {"name": "write_file", "arguments": {"path": "denied.txt", "content": "deneme"}}
        ),
        protocol="v2",
        provenance=origin,
        call_context=origin.call_context,
    )
    assert parsed.calls and not parsed.warnings
    result = ModelResult(
        "fixture", "fixture", parsed.text, 0, True, tool_calls=parsed.calls, web_provenance=origin
    )
    provider = ScriptedProvider([result, model_result("İşlem kullanıcı tarafından reddedildi.")])
    patch_providers(
        monkeypatch, agent_loop, dict.fromkeys(("agent", "a", "b", "c", "hakem"), provider)
    )
    await agent_loop.run_agent(
        "Dosya yaz.",
        _deps(tmp_path, RecordingSink(), mode=ApprovalMode.SECURITY, prompter=AlwaysReject()),
        verify=False,
        self_review=False,
    )
    assert not (tmp_path / "denied.txt").exists()


def _snapshot_page():
    class Locator:
        @property
        def last(self):
            return self

        async def evaluate_all(self, script):
            page.reads += 1
            return [
                {
                    "html": "",
                    "text": "old",
                    "origin": {
                        "role": "data-message-author-role=assistant",
                        "container_id": "old-node",
                        "quoted": False,
                    },
                },
                {
                    "html": "",
                    "text": "accepted",
                    "origin": {
                        "role": "data-message-author-role=assistant",
                        "container_id": "accepted-node",
                        "quoted": False,
                    },
                },
            ]

        async def count(self):
            return 0

        async def is_visible(self):
            return False

    class Page:
        reads = 0

        def locator(self, selector):
            return Locator()

    page = Page()
    return page


async def test_production_request_flag_scope_and_lifecycle_reach_web_parser(tmp_path, monkeypatch):

    from evals.agent_runner import _EvalApproval, _NullPublisher

    from fusion_cli.core.model_capability import ToolSupport
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.execution_policy import policy_for
    from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn

    from .fakes import make_config

    captured = []
    config = make_config(memory_dir=tmp_path)
    config = replace(
        config,
        runtime=replace(config.runtime, emulation_protocol="v2"),
        agent=replace(config.agent, model="chatgpt_web/fixture/auto"),
    )

    async def transport(credential, messages, model, *, context):
        captured.append(context.web_call_context)
        origin = replace(observed_origin(), content_kind="quoted")
        origin = replace(origin, call_context=context.web_call_context)
        return WebTurn(
            "```\n" + render_call({"name": "read_file", "arguments": {"path": "a"}}) + "\n```",
            provenance=origin,
        )

    adapter = WebProviderAdapter(
        model=config.agent.model,
        credential=WebSessionCredential(),
        transport=transport,
        tool_support=ToolSupport.EMULATED,
    )
    provider = EventingProvider(
        adapter, publisher=_NullPublisher(), role="agent", call_id_factory=lambda: "lifecycle-call"
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    deps = loop.AgentDeps(
        config,
        _NullPublisher(),
        _EvalApproval(),
        ToolContext(root=tmp_path),
        conversation_id="receipt-session",
        attempt_id="receipt-attempt",
    )
    result = await loop._call_model(
        [Message("user", "Dosyayı oku")],
        deps,
        deps.base_registry,
        state=loop._State(),
        execution=policy_for(config, config.agent, "Dosyayı oku"),
    )
    assert result.ok and not result.tool_calls and result.parse_warnings
    assert result.web_provenance.call_context == captured[0]
    assert captured == [
        WebCallContext("receipt-session", "receipt-attempt", "receipt-attempt", "lifecycle-call")
    ]

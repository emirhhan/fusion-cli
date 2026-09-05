"""Araç içeriğinin MCP'den modele kadar kaybolmadan taşınması."""

from __future__ import annotations

from fusion_cli.core.tool_content import ToolContent
from fusion_cli.core.tools import Tool, ToolContext, ToolResult
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.tools import ToolRegistry

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self._sink = sink

    def publish(self, event: object) -> None:
        self._sink.handle(event)  # type: ignore[arg-type]


def _build_provider(monkeypatch, provider: ScriptedProvider) -> None:
    def _build(spec, **kwargs):
        del spec, kwargs
        return provider

    monkeypatch.setattr(agent_loop, "build_provider", _build)


async def test_registry_gorseli_sonraki_model_istegine_tasir(monkeypatch, tmp_path):
    registry = ToolRegistry()

    async def inspect(args, context):
        del args, context
        return ToolResult(
            'inceleme\n{"score": 5}\nkaynak: file:///tmp/report.json',
            content=(ToolContent.image("image/png", "aGVsbG8="),),
            structured={"score": 5},
        )

    registry.register(
        Tool(
            name="fixture__inspect",
            description="Görsel inceleme sonucu döndürür.",
            parameters={"type": "object", "properties": {}},
            run=inspect,
        )
    )
    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("fixture__inspect"),)),
            model_result("İnceleme sonucunu kullandım ve görevi tamamladım."),
        ]
    )
    _build_provider(monkeypatch, provider)
    sink = RecordingSink()
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=registry,
    )

    await run_agent("fixture sonucunu incele", deps)

    ikinci_istek = provider.seen_messages[1]
    arac_mesaji = next(message for message in ikinci_istek if message.role == "tool")
    assert arac_mesaji.images == ("data:image/png;base64,aGVsbG8=",)
    assert '"score": 5' in arac_mesaji.content
    assert "file:///tmp/report.json" in arac_mesaji.content

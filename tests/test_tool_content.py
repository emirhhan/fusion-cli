"""Araç içeriğinin MCP'den modele kadar kaybolmadan taşınması."""

from __future__ import annotations

import pytest

from fusion_cli.core.tool_content import ToolContent
from fusion_cli.core.tools import Tool, ToolContext, ToolResult
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.tools import ToolRegistry, build_registry

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


@pytest.mark.parametrize(
    ("etiketler", "gorsel_gider"),
    [(("vision",), True), ((), False)],
    ids=["gorsel-okuyan-model", "gorsel-okuyamayan-model"],
)
async def test_registry_gorseli_sonraki_model_istegine_tasir(
    monkeypatch, tmp_path, etiketler, gorsel_gider
):
    """Ölçüldü (2 Ekim 2026, NIM Nemotron 3 Ultra): görsel okuyamayan modele giden tek bir
    ekran görüntüsü sonraki her isteği "multimodal processing is not enabled" ile düşürdü."""
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
        config=make_config(agent=ModelSpec(name="agent", model="test/model", tags=etiketler)),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=registry,
    )

    await run_agent("fixture sonucunu incele", deps)

    ikinci_istek = provider.seen_messages[1]
    arac_mesaji = next(message for message in ikinci_istek if message.role == "tool")
    if gorsel_gider:
        assert arac_mesaji.images == ("data:image/png;base64,aGVsbG8=",)
        assert "view_image" not in arac_mesaji.content
    else:
        assert arac_mesaji.images == ()
        assert "model görsel okuyamıyor" in arac_mesaji.content
        assert "view_image" in arac_mesaji.content
    assert '"score": 5' in arac_mesaji.content
    assert "file:///tmp/report.json" in arac_mesaji.content


async def test_calistirip_olcen_arac_degisiklikten_sonra_ayni_argumanla_yeniden_calisir(
    monkeypatch, tmp_path
):
    """Ölçüldü (2 Ekim 2026, 8. kabul koşusu): model temayı yazıp `start_preview`'ı yeniden
    çağırdı; tekrar kapısı "zaten yaptın" diye engelledi ve tema hiç etkinleşmedi."""
    registry = build_registry()
    calisma: list[int] = []

    async def calistir(args, context):
        del args, context
        calisma.append(1)
        return ToolResult(f"önizleme {len(calisma)}")

    registry.register(
        Tool(
            name="fixture__preview",
            description="Projeyi çalıştırır ve ölçer.",
            parameters={"type": "object", "properties": {}},
            run=calistir,
            mutating=True,
            reruns_on_change=True,
        )
    )
    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("fixture__preview"),)),
            model_result(tool_calls=(tool_call("write_file", path="a.txt", content="x"),)),
            model_result(tool_calls=(tool_call("fixture__preview"),)),
            # Kabuk adımı da değişikliktir (ölçüldü: ürünler php betiğiyle eklendi).
            model_result(tool_calls=(tool_call("run_shell", command="echo urun >> a.txt"),)),
            model_result(tool_calls=(tool_call("fixture__preview"),)),
            model_result("Önizleme üç kez çalıştı; a.txt yazıldı ve doğrulandı."),
        ]
    )
    _build_provider(monkeypatch, provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=registry,
    )

    await run_agent("a.txt yaz ve önizle", deps)

    assert len(calisma) == 3


async def test_dusen_yazma_kabuk_duzeltmesinden_sonra_yeniden_denenebilir(monkeypatch, tmp_path):
    """Ölçüldü (2 Ekim 2026, 10. kabul koşusu): hedef dizin olduğu için düşen `write_file`,
    dizin `rm -rf` ile kaldırıldıktan sonra TOOL_CALL_DUPLICATE ile engellendi."""
    (tmp_path / "parca.php").mkdir()
    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("write_file", path="parca.php", content="<?php"),)),
            model_result(tool_calls=(tool_call("run_shell", command="rmdir parca.php"),)),
            model_result(tool_calls=(tool_call("write_file", path="parca.php", content="<?php"),)),
            model_result("parca.php yazıldı ve doğrulandı."),
        ]
    )
    _build_provider(monkeypatch, provider)
    deps = AgentDeps(
        config=make_config(),
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=build_registry(),
    )

    await run_agent("parca.php dosyasını yaz", deps)

    ilk = next(m for m in provider.seen_messages[1] if m.role == "tool")
    assert "Bu bir dizin" in ilk.content
    assert (tmp_path / "parca.php").is_file()

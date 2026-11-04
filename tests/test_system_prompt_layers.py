"""Sistem talimatı iki katmanlıdır: dar çekirdek herkese, kapsamlı ilkeler API modeline.

Web/tarayıcı modellerinin bağlamı dardır ve `tests/test_system_prompt_diet.py`
bütçesi yalnız çekirdeğe (`system.md`) uygulanır. Araç çağırabilen API modelleri
ek olarak `system_api.md`'yi alır.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import API_SYSTEM_PROMPT, AgentDeps, run_agent

from .fakes import AlwaysApprove, RecordingSink, ScriptedProvider, make_config, model_result

API_PROMPT = (
    Path(__file__).resolve().parents[1] / "src/fusion_cli/engines/agent/prompts/system_api.md"
)


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self.sink = sink

    def publish(self, event: object) -> None:
        self.sink.handle(event)


def _deps(tmp_path, model: str) -> AgentDeps:
    # Görev haritası boş: seçim doğrudan `agent` rolüne düşer ve sınanan model odur.
    config = make_config(agent=ModelSpec(name="cirak", model=model), task_model_map={})
    return AgentDeps(
        config=config,
        publisher=_Publisher(RecordingSink()),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def test_api_katmani_calisma_ve_konusma_ilkelerini_tasir() -> None:
    text = API_PROMPT.read_text(encoding="utf-8")

    for phrase in (
        "İlk araçtan önce",
        "ara not",
        "Bitişte önce sonucu söyle",
        "aynı argümanla ikinci kez çağırma",
        "resmi\n  dokümandan",
        "Kapsam",
        "veri say",
    ):
        assert phrase in text
    assert text.startswith("<api-calisma-ilkeleri>\n")
    assert text.endswith("</api-calisma-ilkeleri>\n")


async def test_api_modeli_kapsamli_katmani_alir(monkeypatch, tmp_path) -> None:
    from fusion_cli.engines.agent import loop

    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda _spec, **_kwargs: provider)

    await run_agent("Merhaba", _deps(tmp_path, "nvidia_nim/ornek-model"))

    system = provider.seen_messages[0][0].content
    assert API_SYSTEM_PROMPT.strip() in system
    assert system.startswith("<kimlik>")


async def test_web_modeli_yalniz_dar_cekirdegi_alir(monkeypatch, tmp_path) -> None:
    from fusion_cli.engines.agent import loop

    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda _spec, **_kwargs: provider)

    await run_agent("Merhaba", _deps(tmp_path, "gemini_web/main/auto"))

    system = provider.seen_messages[0][0].content
    assert "<api-calisma-ilkeleri>" not in system


async def test_ajan_guncel_tarihi_enjekte_edilen_saatten_alir(monkeypatch, tmp_path) -> None:
    from fusion_cli.engines.agent import loop

    from .test_turn_deadline import FakeClock

    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda _spec, **_kwargs: provider)
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    # Her saat diliminde yerel 4 Kasım öğlenini temsil eden sabit test saati.
    deps.clock = FakeClock(datetime(2026, 11, 4, 12).timestamp())

    await run_agent("Güncel bir rapor hazırla", deps)

    system = provider.seen_messages[0][0].content
    assert "2026-11-04" in system

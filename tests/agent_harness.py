"""Gerçek agent döngüsünü betiklenmiş modelle süren ortak koşum takımı.

Sahte olan TEK şey sağlayıcıdır. Araç kayıt defteri, onay politikası, sözleşme
doğrulaması, tekrar kapısı, boşta-tur kapısı, kanıt kapısı ve dosya sistemi
gerçektir — kilitlenmeler bu kapıların ETKİLEŞİMİNDEN doğuyor ve ancak hepsi
birlikte koştuğunda görülüyor. Ağ erişimi yoktur.

Birim testler bu sınıfı göremez: `_targeted_edit_required` için yazılmış birim
testi geçerken gerçek döngü `files.py`'deki ikinci bir kapıda kilitleniyordu.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.events import ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps

from .fakes import AlwaysApprove, RecordingSink, make_config

#: Web sağlayıcı kimliği. Kapıların bir kısmı (toptan yazma, tur/çağrı tavanları)
#: YALNIZCA web modellerinde çalışır; API modeliyle koşmak onları hiç göstermez.
WEB_MODEL = "gemini_web/pro"

#: Boşta-tur kapısı burada bilinçli olarak DAR tutulur (gerçek varsayılan gibi):
#: kilitlenme ancak kapı gerçekten devredeyken görülebilir.
IDLE_ROUNDS = 3
MAX_STEPS = 20


class Publisher:
    """`EventPublisher` protokolünün kayıt tutan sahtesi."""

    def __init__(self, sink: RecordingSink) -> None:
        self._sink = sink

    def publish(self, event: object) -> None:
        self._sink.handle(event)


def web_deps(tmp_path: Path, sink: RecordingSink, **runtime: object) -> AgentDeps:
    """Web modeliyle çalışan gerçek bağımlılıklar; `runtime` ile ayar ezilebilir."""
    ayarlar: dict[str, object] = {
        "agent_max_idle_rounds": IDLE_ROUNDS,
        "agent_max_steps": MAX_STEPS,
    }
    ayarlar.update(runtime)
    config = make_config(
        agent=ModelSpec(name="agent", model=WEB_MODEL),
        web_sessions=(
            WebSessionConfig(model=WEB_MODEL, transport="browser", tool_support="emulated"),
        ),
        runtime=ayarlar,
    )
    return AgentDeps(
        config=config,
        publisher=Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def install_provider(monkeypatch: pytest.MonkeyPatch, provider: object) -> object:
    """Motorun sağlayıcı kurucusunu betiklenmiş sağlayıcıyla değiştir."""
    monkeypatch.setattr(agent_loop, "build_provider", lambda *a, **k: provider)
    return provider


def tool_events(sink: RecordingSink) -> list[ToolExecuted]:
    return [olay for olay in sink.events if isinstance(olay, ToolExecuted)]


def blocked_tools(sink: RecordingSink) -> list[str]:
    """Bloklanmış ya da başarısız olmuş araç adları, çağrı sırasıyla."""
    return [
        olay.name
        for olay in tool_events(sink)
        if olay.outcome in (ToolOutcome.BLOCKED, ToolOutcome.FAILED)
    ]


def blocking_outputs(sink: RecordingSink) -> list[str]:
    """Modeli engelleyen araç sonuçlarının metinleri."""
    return [
        olay.output
        for olay in tool_events(sink)
        if olay.outcome in (ToolOutcome.BLOCKED, ToolOutcome.FAILED)
    ]

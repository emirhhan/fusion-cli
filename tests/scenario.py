"""Senaryo koşumu — bir turu uçtan uca çalıştırıp TERMİNAL DÖKÜMÜNÜ üretir.

Neden var: davranış hataları (öncü metnin kaybolması, çerçevenin cevaba sızması,
aynı cevabın iki kez basılması) birim testlerde görünmez. Bunlar sağlayıcı
ayrıştırması, motor kapıları ve render'ın ETKİLEŞİMİNDEN doğar ve ancak üçü
birlikte koşup ekrana basıldığında fark edilir. Eskiden bu hatalar yalnızca
kullanıcı canlı bir oturumda gördüğünde ortaya çıkıyordu.

Sahte olan TEK şey taşımadır: model yanıtı düz metin olarak verilir. Bu metin
gerçek `WebProviderAdapter` ile ayrıştırılır (taklit araç sözleşmesi), gerçek
agent döngüsünden geçer (onay, refleksiyon, kanıt kapısı, otomatik devam),
gerçek araç kayıt defterini ve dosya sistemini kullanır, gerçek
`ConsoleRenderer` ile basılır. Ağ erişimi yoktur.

Elle koşturmak için:

    python -m tests.scenario            # tüm senaryolar
    python -m tests.scenario ad-parçası # yalnızca eşleşenler
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, AgentOutcome, run_agent
from fusion_cli.providers.eventing import EventingProvider
from fusion_cli.providers.web_browser import strip_role_headers
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential
from fusion_cli.ui.renderer import ConsoleRenderer

from .fakes import AlwaysApprove, make_config

#: Senaryolar web modeliyle koşar: öncü metin, taklit araç sözleşmesi ve web'e
#: özel kapılar yalnızca orada devrededir.
WEB_MODEL = "gemini_web/pro"

#: Döküm genişliği. Gerçek terminale yakın; satır kaydırma davranışı da görünür.
CONSOLE_WIDTH = 100


@dataclass(frozen=True, slots=True)
class Scenario:
    """Tek bir turun betiği.

    `replies` modelin SIRAYLA vereceği ham yanıtlardır — tıpkı web arayüzünden
    döneceği gibi. Liste tükenirse sonuncusu tekrarlanır: kapılar turu
    uzatabildiği için kaç çağrı olacağı önceden bilinmez.
    """

    name: str
    task: str
    replies: tuple[str, ...]
    #: Tur başlamadan çalışma alanına yazılacak dosyalar.
    files: dict[str, str] = field(default_factory=dict)
    #: Bu senaryonun neyi göstermesi beklendiği — dökümü okurken pusula.
    watch: str = ""


@dataclass(frozen=True, slots=True)
class Run:
    """Bir senaryonun sonucu: kullanıcının gördüğü döküm + turun muhasebesi."""

    scenario: Scenario
    transcript: str
    outcome: AgentOutcome
    model_calls: int

    @property
    def summary(self) -> str:
        return (
            f"model çağrısı: {self.model_calls} · araç: {self.outcome.tool_calls_made} · "
            f"mutasyon: {self.outcome.mutating_tool_calls_made} · "
            f"değişiklik yok: {self.outcome.made_no_changes}"
        )


class _ScriptedBrowser:
    """Betiklenmiş web taşıması.

    Gerçek tarayıcı yerine sıradaki metni döndürür, ama gerçek taşımanın
    yaptığı SON İŞLEMİ de yapar: rol başlıklarını ayıklar. Böylece çerçeve
    sızıntısı senaryolarda gerçekten ölçülebilir.
    """

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self.calls = 0

    async def __call__(self, credential: object, messages: object, model: str) -> str:
        index = min(self.calls, len(self._replies) - 1)
        self.calls += 1
        return strip_role_headers(self._replies[index])


class _Publisher:
    def __init__(self, sink: ConsoleRenderer) -> None:
        self._sink = sink

    def publish(self, event: object) -> None:
        self._sink.handle(event)


def _deps(root: Path, renderer: ConsoleRenderer) -> AgentDeps:
    config = make_config(
        agent=ModelSpec(name="agent", model=WEB_MODEL),
        web_sessions=(
            WebSessionConfig(model=WEB_MODEL, transport="browser", tool_support="emulated"),
        ),
        runtime={"max_tokens": 2048, "agent_max_steps": 24},
    )
    return AgentDeps(
        config=config,
        publisher=_Publisher(renderer),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=root),
    )


async def run_scenario(scenario: Scenario, root: Path) -> Run:
    """Senaryoyu çalıştır ve kullanıcının göreceği dökümü döndür."""
    for name, content in scenario.files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=CONSOLE_WIDTH, no_color=True)
    # `live_progress=False`: canlı gösterge dönen imleç karakterlerini döküme
    # karıştırır ve okunmaz hale getirir. Ölçülen şey basılan METİNDİR.
    renderer = ConsoleRenderer(console, live_progress=False, show_call_details=False)

    transport = _ScriptedBrowser(scenario.replies)
    provider = _build_provider(transport, renderer)

    original = agent_loop.build_provider
    agent_loop.build_provider = lambda *args, **kwargs: provider  # type: ignore[assignment]
    try:
        outcome = await run_agent(scenario.task, _deps(root, renderer))
    finally:
        agent_loop.build_provider = original  # type: ignore[assignment]

    _publish_turn_end(renderer, outcome)
    return Run(
        scenario=scenario,
        transcript=buffer.getvalue(),
        outcome=outcome,
        model_calls=transport.calls,
    )


def _publish_turn_end(renderer: ConsoleRenderer, outcome: AgentOutcome) -> None:
    """Turun ARDINDAN gelen olayları gerçek sarmalayıcıyla AYNI sırada yayınla.

    `run_agent` bu olayları kendisi yayınlamaz; `cli/session.run_agent_task` ve
    REPL döngüsü yayınlar. Koşum onları taklit etmezse döküm gerçeği yansıtmaz —
    örneğin kanıt kapısına takılan bir turda kullanıcının gördüğü hata satırı
    dökümde hiç görünmez ve ekran boşmuş gibi okunur.
    """
    from fusion_cli.core.events import ErrorOccurred, NoFileChanges, TurnFinished
    from fusion_cli.ui import messages as ui_messages

    if not outcome.final_text.strip():
        renderer.handle(ErrorOccurred(ui_messages.AGENT_EMPTY_ANSWER, fatal=True))
    elif not outcome.ok:
        renderer.handle(ErrorOccurred(outcome.final_text, fatal=False))
    if outcome.ok and outcome.made_no_changes:
        renderer.handle(NoFileChanges())
    renderer.handle(TurnFinished())


def _build_provider(transport: _ScriptedBrowser, renderer: ConsoleRenderer) -> object:
    """Gerçek web adaptörünü gerçek olay sarmalayıcısıyla kur."""
    adapter = WebProviderAdapter(
        model=WEB_MODEL,
        credential=WebSessionCredential(),
        transport=transport,
        tool_support=ToolSupport.EMULATED,
    )
    return EventingProvider(adapter, publisher=_Publisher(renderer), role="agent")


async def _main(pattern: str = "") -> None:
    import tempfile

    from .scenarios import ALL_SCENARIOS

    secilen = [s for s in ALL_SCENARIOS if pattern in s.name] if pattern else ALL_SCENARIOS
    for scenario in secilen:
        with tempfile.TemporaryDirectory() as tmp:
            run = await run_scenario(scenario, Path(tmp))
        print("=" * CONSOLE_WIDTH)
        print(f"SENARYO: {scenario.name}")
        if scenario.watch:
            print(f"BAKILACAK: {scenario.watch}")
        print("-" * CONSOLE_WIDTH)
        print(run.transcript.rstrip())
        print("-" * CONSOLE_WIDTH)
        print(run.summary)
        print()


if __name__ == "__main__":  # pragma: no cover - elle çalıştırma yolu
    import sys

    asyncio.run(_main(sys.argv[1] if len(sys.argv) > 1 else ""))

"""Gerçek agent köprüsü — bir isteği fusion agent motoruyla headless çalıştırır.

Bu modül ağ/model'e çıkar (gerçek ölçüm bunu gerektirir); bu yüzden testlerde
kullanılmaz, yalnızca `python -m evals run` gerçek koşuda kurar. Yürütücünün gözlem
mantığı ise sahte koşucuyla ayrıca test edilir.

Headless kurulum: onay OTOMATİK (yıkıcı komut reddedilir — izole dizin bile olsa
sistemi koruruz), etkileşim yok (ask_user sunulmaz), bellek yok (ölçüm belleği
kirletmesin ve öğrenme yan etkisi olmasın), olaylar no-op yayıncıya gider.
"""

from __future__ import annotations

from pathlib import Path

from evals.executor import AgentRunObservation
from fusion_cli.config.models import Config
from fusion_cli.core.events import Event
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import run_agent
from fusion_cli.engines.agent.approval import ApprovalRequest, Decision
from fusion_cli.engines.agent.loop import AgentDeps


class _NullPublisher:
    """Olayları yutan yayıncı: ölçümde ilerleme çıktısı gerekmez."""

    def publish(self, event: Event) -> None:
        return None


class _EvalApproval:
    """Ürünün auto kipiyle AYNI kararı verir; soru sorulacak her şeyi reddeder.

    Ölçüm headless'tır: soru sorulamaz. "Sorulurdu" durumunu izin saymak koşucuyu
    üründen daha gevşek yapar ve ölçüm yanıltıcı olur — nitekim oldu: kök dışına
    yazan bir kabuk yönlendirmesi (`echo x > ../y`) burada sessizce geçti, oysa
    gerçek kullanıcıya sorulup reddedilebilirdi.

    Karar `AutoApproval` ile aynı iki koşula bakar (bkz. `engines.agent.approval`):
    yıkıcı değil VE gözetimsiz çalışmaya uygun. Değilse reddedilir.
    """

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.danger is None and request.unattended_safe:
            return Decision.ALLOW
        return Decision.DENIED


class FusionAgentRunner:
    """İsteği izole bir kök dizinde agent motoruyla çalıştırır."""

    def __init__(self, config: Config) -> None:
        self._config = config

    async def run(self, request: str, *, root: Path) -> AgentRunObservation:
        deps = AgentDeps(
            config=self._config,
            publisher=_NullPublisher(),
            policy=_EvalApproval(),
            tool_context=ToolContext(root=root),
            asker=None,
            code_index=None,
            lessons=None,
            capabilities=None,
        )
        outcome = await run_agent(request, deps)
        # Model çağrısı ~ araç turu + son cevap turu (metrik için makul bir tahmin).
        return AgentRunObservation(
            output_text=outcome.final_text, model_calls=outcome.tool_calls_made + 1
        )

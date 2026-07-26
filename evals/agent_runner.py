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
from evals.transcript import TranscriptRecorder
from fusion_cli.config.models import Config
from fusion_cli.core.events import Event
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import is_rate_limit_error
from fusion_cli.engines.agent import run_agent
from fusion_cli.engines.agent.approval import ApprovalRequest, Decision
from fusion_cli.engines.agent.loop import AgentDeps


class _NullPublisher:
    """Olayları yutan yayıncı: ölçümde ilerleme çıktısı gerekmez."""

    def publish(self, event: Event) -> None:
        return None


class _EvalApproval:
    """Headless onay politikası — görevin duruşuna göre iki farklı kullanıcıyı modeller.

    `permissive`: olağan işe EVET diyen kullanıcı. Yıkıcı komut yine reddedilir
    (izole dizin bile olsa sistemi koruruz). Yetenek ölçümü budur — gerçek kullanıcı
    `python -c ...` ya da `chmod +x` istendiğinde onaylar; reddetmek agent'ın
    yapabildiğini olduğundan AZ gösterir.

    `strict`: hiçbir şeye onay VERMEYEN kullanıcı; `AutoApproval` sorsaydı reddedilir.
    Güvenlik ölçümü budur — sorulan soru "agent yasak işi ONAY ALMADAN yapabiliyor mu".

    İkisi tek politikayla ölçülemez: sıkı politika yetenek görevlerini kırar, gevşek
    politika güvenlik görevlerini anlamsızlaştırır. Ölçüldü (2026-07-26): tek sıkı
    politikayla başarı %85.7'den %71.4'e düştü ve düşüşün tamamı meşru işlerdi.
    """

    def __init__(self, strict: bool = False) -> None:
        self._strict = strict

    async def decide(self, request: ApprovalRequest) -> Decision:
        if request.danger is not None:
            return Decision.DENIED
        if self._strict and not request.unattended_safe:
            return Decision.DENIED
        return Decision.ALLOW


class FusionAgentRunner:
    """İsteği izole bir kök dizinde agent motoruyla çalıştırır."""

    def __init__(self, config: Config) -> None:
        self._config = config

    async def run(
        self,
        request: str,
        *,
        root: Path,
        strict_approval: bool = False,
        transcript: Path | None = None,
    ) -> AgentRunObservation:
        # Transkript turda NE OLDUĞUNU kaydeder; başarısızlık sonradan teşhis
        # edilebilsin diye. Yoksa yayıncı olayları yutar (ölçümde çıktı gerekmez).
        kayit = TranscriptRecorder(transcript) if transcript is not None else None
        deps = AgentDeps(
            config=self._config,
            publisher=kayit if kayit is not None else _NullPublisher(),
            policy=_EvalApproval(strict=strict_approval),
            tool_context=ToolContext(root=root),
            asker=None,
            code_index=None,
            lessons=None,
            capabilities=None,
        )
        outcome = await run_agent(request, deps)
        if kayit is not None:
            kayit.close()
        # Kota hatası görev başarısızlığı değildir; ayırt edilmezse ölçüm sessizce
        # bozulur (ölçüldü: kota tükenirken model çağrısı 8.6→5.8→1.0'a düştü ve
        # düşüş yanlışlıkla bir kod değişikliğine atfedildi).
        kota = not outcome.ok and is_rate_limit_error(outcome.final_text)
        # Model çağrısı ~ araç turu + son cevap turu (metrik için makul bir tahmin).
        return AgentRunObservation(
            output_text=outcome.final_text,
            model_calls=outcome.tool_calls_made + 1,
            rate_limited=kota,
            rate_limit_detail=outcome.final_text if kota else "",
        )

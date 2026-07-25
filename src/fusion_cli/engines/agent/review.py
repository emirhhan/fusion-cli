"""Öz-eleştiri — turu hızlı bir denetçi modele kontrol ettirir.

Denetçi "TAMAM" derse hiçbir şey olmaz. Somut bir sorun bulursa tek paragraflık bir
düzeltme talimatı üretir ve motor agent'a TEK bir düzeltici tur verir. Sonsuz
düzeltme döngüsü bilinçli olarak yoktur: ikinci bir denetim yapılmaz.

Denetim başarısız olursa (zaman aşımı, bozuk yanıt) sessizce atlanır — öz-eleştiri
bir iyileştirmedir, turu düşürmesi kabul edilemez.
"""

from __future__ import annotations

from pathlib import Path

from ...config.models import Config
from ...core.events import EventPublisher
from ...core.types import CompletionRequest, Message, ModelResult
from ...providers.factory import build_provider
from . import history

_PROMPT = (Path(__file__).parent / "prompts" / "review.txt").read_text(encoding="utf-8")

#: Denetçinin "sorun yok" cevabı.
CLEAN_VERDICT = "TAMAM"
#: Bundan kısa bir cevap anlamlı bir talimat taşıyamaz.
MIN_INSTRUCTION_CHARS = 8


def parse_feedback(text: str) -> str:
    """Denetçi çıktısını düzeltme talimatına çevir; sorun yoksa boş metin."""
    verdict = (text or "").strip()
    if not verdict or len(verdict) < MIN_INSTRUCTION_CHARS:
        return ""
    if verdict.upper().startswith(CLEAN_VERDICT):
        return ""
    return verdict


async def review_turn(
    task: str,
    final_text: str,
    messages: list[Message],
    *,
    config: Config,
    publisher: EventPublisher | None = None,
) -> str:
    """Turu denetle. Düzeltme gerekiyorsa talimatı, gerekmiyorsa boş metin döner."""
    trace = history.transcript(messages)
    if not trace.strip() and not final_text.strip():
        return ""

    prompt = (
        _PROMPT.replace("{task}", task)
        .replace("{trace}", trace)
        .replace("{final}", final_text[:1500])
    )
    result = await _ask(prompt, config, publisher)
    return parse_feedback(result.text) if result.ok else ""


async def _ask(prompt: str, config: Config, publisher: EventPublisher | None) -> ModelResult:
    request = CompletionRequest(
        messages=(Message("user", prompt),),
        temperature=config.runtime.utility_temperature,
        max_tokens=config.runtime.judge_max_tokens,
        timeout_s=config.runtime.judge_timeout_s,
        max_retries=config.runtime.max_retries,
    )
    # Arka plan işi: ilerleme satırı GÖSTERİLMEZ ama harcadığı token muhasebeye girer.
    provider = build_provider(
        config.judge,
        publisher=publisher,
        hedge_delay_s=config.runtime.hedge_delay_s,
        background=True,
    )
    return await provider.complete(request)

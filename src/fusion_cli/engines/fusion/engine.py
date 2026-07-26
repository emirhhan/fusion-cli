"""Fusion motoru: aynı görevi birden çok modele sorup en iyi cevabı üretir.

Akış:

1. **Aday sıralama** — görev tipine göre tercih edilen model öne alınır.
2. **Paralel çağrı** — tüm adaylar aynı anda çalışır; yavaşlar zaman bütçesiyle
   kesilir (`core.concurrency.gather_with_cutoff`).
3. **Kısa devre** — tek başarılı cevap varsa hakem hiç çağrılmaz.
4. **Hakem ‖ sentez** — ikisi birbirine bağımlı DEĞİLDİR (ikisi de yalnızca aday
   cevaplarını okur), bu yüzden PARALEL çalışır. Gecikme = max(hakem, sentez),
   toplamları değil.
5. **Güvenli düşüş** — hakem zaman aşımına uğrar ya da bozuk çıktı verirse sezgisel
   kazanan seçilir; sentez cevabı yine üretilir. Kullanıcı hiçbir senaryoda beklemede
   kalmaz.

Motor konsolu tanımaz: ilerlemeyi olay olarak yayınlar.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from ...config.models import Config
from ...core.concurrency import gather_with_cutoff
from ...core.events import CandidatesStarted, EventPublisher, JudgingStarted
from ...core.memory import Outcome, PerformanceMemory
from ...core.types import (
    CompletionRequest,
    FusionResult,
    Message,
    ModelResult,
    ModelSpec,
    Verdict,
    VerdictSource,
)
from ...providers.factory import build_provider
from .judge import parse_verdict

_PROMPTS = Path(__file__).parent / "prompts"
_JUDGE_PROMPT = (_PROMPTS / "judge.txt").read_text(encoding="utf-8")
_SYNTHESIS_PROMPT = (_PROMPTS / "synthesis.txt").read_text(encoding="utf-8")

#: Hakemin beklemeye değer bulunması için gereken en az başarılı aday sayısı.
_MIN_FOR_JUDGE = 2


async def run_fusion(
    task: str,
    config: Config,
    *,
    publisher: EventPublisher,
    task_type: str = "general",
    synthesis: bool | None = None,
    memory: PerformanceMemory | None = None,
) -> FusionResult:
    """Görevi tüm adaylara sorup hakem + sentez ile nihai cevabı üret.

    `memory` verilirse aday sıralaması geçmiş başarıya göre iyileşir ve tur sonunda
    her adayın performansı kaydedilir — kapalı bir öğrenme döngüsü.
    """
    runtime = config.runtime
    specs = order_candidates(config, task_type, memory=memory)
    use_synthesis = runtime.synthesis if synthesis is None else synthesis

    publisher.publish(CandidatesStarted(names=tuple(spec.name for spec in specs)))
    candidates = await _call_candidates(task, specs, config, publisher=publisher)
    usable = [result for result in candidates if result.ok and result.text]

    if len(usable) < runtime.min_successful_candidates:
        return _no_winner(task, task_type, candidates)
    if len(usable) < _MIN_FOR_JUDGE:
        return _single_winner(task, task_type, candidates, usable[0])

    verdict, synthesized = await _judge_and_synthesize(
        task, usable, config, publisher=publisher, use_synthesis=use_synthesis
    )
    winning = next(result for result in usable if result.name == verdict.winner)
    result = FusionResult(
        task=task,
        task_type=task_type,
        winner=verdict.winner,
        final_answer=synthesized or winning.text,
        source=VerdictSource.JUDGE if verdict.parsed else VerdictSource.FALLBACK,
        candidates=tuple(candidates),
        reason=verdict.reason,
        scores=verdict.scores,
        synthesized=synthesized is not None,
    )
    _remember(result, memory)
    return result


def _remember(result: FusionResult, memory: PerformanceMemory | None) -> None:
    """Her başarılı adayın performansını kaydet (öz-öğrenme verisi)."""
    if memory is None:
        return
    for candidate in result.successful:
        memory.record(
            Outcome(
                task=result.task,
                task_type=result.task_type,
                model_name=candidate.name,
                # Hakem puan vermediyse kazanana 1.0, diğerlerine nötr 0.5 yazılır.
                score=result.scores.get(
                    candidate.name, 1.0 if candidate.name == result.winner else 0.5
                ),
                latency_ms=candidate.latency_ms,
                tokens=candidate.usage.total_tokens,
                won=candidate.name == result.winner,
            )
        )


# --------------------------------------------------------------------------- #
# Aday aşaması
# --------------------------------------------------------------------------- #


def order_candidates(
    config: Config, task_type: str, *, memory: PerformanceMemory | None = None
) -> tuple[ModelSpec, ...]:
    """Tercih edilen adayı öne al; sıralama kararlı kalır.

    Öncelik sırası: (1) bellekte bu görev tipinde en iyi olan model, (2) yapılandırmadaki
    `task_model_map`. Bellek zamanla yapılandırmayı ezer — sistem kullandıkça öğrenir.
    """
    preferred = _preferred_names(config, task_type, memory)
    if not preferred:
        return config.candidates
    return tuple(sorted(config.candidates, key=lambda spec: _rank(spec.name, preferred)))


def _preferred_names(config: Config, task_type: str, memory: PerformanceMemory | None) -> list[str]:
    known = {spec.name for spec in config.candidates}
    names: list[str] = []
    if memory is not None:
        best = memory.best_model(task_type)
        if best in known:
            names.append(str(best))
    mapped = config.task_model_map.get(task_type)
    if mapped in known and mapped not in names:
        names.append(str(mapped))
    return names


def _rank(name: str, preferred: list[str]) -> int:
    return preferred.index(name) if name in preferred else len(preferred)


async def _call_candidates(
    task: str,
    specs: tuple[ModelSpec, ...],
    config: Config,
    *,
    publisher: EventPublisher,
) -> list[ModelResult]:
    runtime = config.runtime
    request = _request(task, config, max_tokens=runtime.max_tokens)

    def _factory(spec: ModelSpec) -> Callable[[], Awaitable[ModelResult]]:
        # Sağlayıcı closure'a bağlanır; `gather_with_cutoff` çağrıyı kendi başlatır.
        provider = build_provider(spec, publisher=publisher, hedge_delay_s=runtime.hedge_delay_s)
        return lambda: provider.complete(request)

    return await gather_with_cutoff(
        [_factory(spec) for spec in specs],
        is_success=lambda result: result.ok and bool(result.text),
        enough_success=max(runtime.min_successful_candidates, min(_MIN_FOR_JUDGE, len(specs))),
        grace_s=runtime.straggler_grace_s,
        hard_cap_s=runtime.candidate_hard_cap_s,
    )


# --------------------------------------------------------------------------- #
# Hakem + sentez aşaması
# --------------------------------------------------------------------------- #


#: Aday metnini güvenilmeyen-veri bloğu içine alırken kullanılan sınır işaretleri.
#: Aday bunları kendisi üretirse bloktan "çıkıp" talimat alanına geçmiş gibi
#: görünebilir; bu yüzden metinde geçtikleri yerde etkisizleştirilirler.
_BLOCK_MARKERS = ("<<<", ">>>")


def sanitize_candidate(text: str) -> str:
    """Aday cevabını güvenilmeyen-veri bloğuna girmeden önce etkisizleştir.

    Yalnızca sınır işaretleri kırılır — cevabın anlamı korunmalıdır, aday metnini
    kırpmak ya da yeniden yazmak hakemin değerlendireceği şeyi bozardı.
    """
    temiz = text
    for marker in _BLOCK_MARKERS:
        temiz = temiz.replace(marker, marker[0] + "\u200b" + marker[1:])
    return temiz


def synthesis_prompt(task: str, answers: str, *, verdict: Verdict | None) -> str:
    """Sentez promptunu kur; hakem kararı varsa onu da taşı.

    `verdict` None ise HIZLI kip: hakem ve sentez paralel çalışır, sentez kararı
    göremez. Doğrulanmış kipte karar buraya girer ve sentez hangi adayın kazandığını,
    hangisinin zayıf bulunduğunu bilerek birleştirir — paralel kipte tüm cevaplar
    eşit ağırlıkta okunuyor ve düşük puanlı adayın hatası nihai cevaba sızabiliyordu.

    Ayrıştırılamamış karar (hakem bozuk JSON verdi, sezgisel kazanan seçildi)
    TAŞINMAZ: onu "hakem böyle dedi" diye sunmak modele olmayan bir otorite verir.
    """
    dolu = _fill(_SYNTHESIS_PROMPT, task, answers)
    if verdict is None or not verdict.parsed:
        return dolu
    puanlar = ", ".join(f"{ad}: {puan}" for ad, puan in verdict.scores.items())
    karar_blogu = (
        "\n\nHAKEM DEĞERLENDİRMESİ (güvenilir — bu sistemin kendi hakem modelinden gelir):\n"
        f"- Kazanan: {verdict.winner}\n"
        f"- Puanlar: {puanlar}\n"
        f"- Gerekçe: {verdict.reason}\n"
        "Kazananı temel al; düşük puanlı cevaplardan YALNIZCA doğruluğundan emin "
        "olduğun eksik bilgileri ekle. Zayıf bulunan bir cevabın hatasını taşıma."
    )
    return dolu + karar_blogu


async def _judge_and_synthesize(
    task: str,
    usable: list[ModelResult],
    config: Config,
    *,
    publisher: EventPublisher,
    use_synthesis: bool,
) -> tuple[Verdict, str | None]:
    answers = "\n\n".join(
        f"### Model: {result.name}\n{sanitize_candidate(result.text)}" for result in usable
    )
    names = [result.name for result in usable]

    publisher.publish(JudgingStarted(with_synthesis=use_synthesis))
    if config.runtime.verified_synthesis and use_synthesis:
        return await _verified(task, answers, names, config, publisher)
    verdict_result, synthesis_result = await asyncio.gather(
        _judge(task, answers, config, publisher),
        _synthesize(task, answers, config, publisher) if use_synthesis else _none(),
    )

    if verdict_result is not None and verdict_result.ok:
        verdict = parse_verdict(verdict_result.text, names)
    else:
        verdict = Verdict(winner=names[0], scores={}, reason="", parsed=False)
    synthesized = (
        synthesis_result.text
        if synthesis_result is not None and synthesis_result.ok and synthesis_result.text
        else None
    )
    return verdict, synthesized


async def _judge(
    task: str, answers: str, config: Config, publisher: EventPublisher
) -> ModelResult | None:
    """Hakemi SIKI bir son tarihle çağır. Yetişemezse None döner ve sezgisel kazanan seçilir."""
    request = _request(
        task,
        config,
        max_tokens=config.runtime.judge_max_tokens,
        prompt=_fill(_JUDGE_PROMPT, task, answers),
        timeout_s=config.runtime.judge_timeout_s,
        temperature=config.runtime.judge_temperature,
    )
    # Arka plan işi: ilerleme satırı gösterilmez ama harcadığı token muhasebeye girer.
    provider = build_provider(
        config.judge,
        publisher=publisher,
        hedge_delay_s=config.runtime.hedge_delay_s,
        background=True,
    )
    try:
        return await asyncio.wait_for(
            provider.complete(request), timeout=config.runtime.judge_timeout_s + 2
        )
    except TimeoutError:
        return None


async def _synthesize(
    task: str,
    answers: str,
    config: Config,
    publisher: EventPublisher,
    verdict: Verdict | None = None,
) -> ModelResult:
    request = _request(
        task,
        config,
        max_tokens=config.runtime.max_tokens,
        prompt=synthesis_prompt(task, answers, verdict=verdict),
    )
    provider = build_provider(
        config.judge,
        publisher=publisher,
        hedge_delay_s=config.runtime.hedge_delay_s,
        background=True,
    )
    return await provider.complete(request)


async def _verified(
    task: str,
    answers: str,
    names: list[str],
    config: Config,
    publisher: EventPublisher,
) -> tuple[Verdict, str | None]:
    """Doğrulanmış kip: önce hakem, SONRA sentez.

    Gecikme artar (iki aşama seri çalışır) ve bu bilinçli bir takastır: fusion
    zaten "yavaş ama dikkatli" motordur, hız isteyen agent kipini kullanır.
    Hakem yetişemezse sezgisel kazanana düşülür ve sentez yine çalışır — kullanıcı
    hiçbir senaryoda cevapsız kalmaz.
    """
    verdict_result = await _judge(task, answers, config, publisher)
    if verdict_result is not None and verdict_result.ok:
        verdict = parse_verdict(verdict_result.text, names)
    else:
        verdict = Verdict(winner=names[0], scores={}, reason="", parsed=False)

    synthesis_result = await _synthesize(task, answers, config, publisher, verdict)
    synthesized = synthesis_result.text if synthesis_result.ok and synthesis_result.text else None
    return verdict, synthesized


async def _none() -> None:
    """`asyncio.gather` içinde sentez kapalıyken kullanılan boş dal."""
    return None


# --------------------------------------------------------------------------- #
# Yardımcılar
# --------------------------------------------------------------------------- #


def _fill(template: str, task: str, answers: str) -> str:
    return template.replace("{task}", task).replace("{answers}", answers)


def _request(
    task: str,
    config: Config,
    *,
    max_tokens: int,
    prompt: str | None = None,
    timeout_s: float | None = None,
    temperature: float | None = None,
) -> CompletionRequest:
    runtime = config.runtime
    return CompletionRequest(
        messages=(Message("user", prompt if prompt is not None else task),),
        temperature=runtime.temperature if temperature is None else temperature,
        max_tokens=max_tokens,
        timeout_s=runtime.request_timeout_s if timeout_s is None else timeout_s,
        max_retries=runtime.max_retries,
    )


def _no_winner(task: str, task_type: str, candidates: list[ModelResult]) -> FusionResult:
    return FusionResult(
        task=task,
        task_type=task_type,
        winner="",
        final_answer="",
        source=VerdictSource.NONE,
        candidates=tuple(candidates),
    )


def _single_winner(
    task: str, task_type: str, candidates: list[ModelResult], only: ModelResult
) -> FusionResult:
    return FusionResult(
        task=task,
        task_type=task_type,
        winner=only.name,
        final_answer=only.text,
        source=VerdictSource.SINGLE,
        candidates=tuple(candidates),
        scores={only.name: 1.0},
    )

"""Öz-eleştiri — turu hızlı bir denetçi modele kontrol ettirir.

Denetçi "TAMAM" derse hiçbir şey olmaz. Somut bir sorun bulursa tek paragraflık bir
düzeltme talimatı üretir ve motor agent'a TEK bir düzeltici tur verir. Sonsuz
düzeltme döngüsü bilinçli olarak yoktur: ikinci bir denetim yapılmaz.

Denetim başarısız olursa (zaman aşımı, bozuk yanıt) düzeltme atlanır; bu durum
"sorun yok" kararından ayrı bildirilir.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path

from ...config.model_lookup import configured_model_specs
from ...config.models import Config
from ...core.clock import SystemClock
from ...core.events import EventPublisher
from ...core.evidence import CriterionEvidence
from ...core.rate_control import RateControl
from ...core.redaction import redact
from ...core.types import CompletionRequest, Message, ModelResult
from ...providers.factory import build_provider
from ...providers.web_registry import web_registry_for
from . import history
from .evidence_handoff import DIFF_CHAR_LIMIT, evidence_text

_PROMPT_PATH = Path(__file__).parent / "prompts" / "review.txt"

#: Denetçinin "sorun yok" cevabı.
CLEAN_VERDICT = "TAMAM"
#: Bundan kısa bir cevap anlamlı bir talimat taşıyamaz.
MIN_INSTRUCTION_CHARS = 8
_GROUNDED_NIM_REASONING_BUDGET = 1024

#: Denetçiye gösterilecek oturum izinin uzunluğu.
#:
#: Varsayılan iz bütçesi (3.000 karakter) yalnızca ~10 adım taşır. Uzun bir turda
#: denetçi üretilen dosyaları hiç görmeden "TAMAM" diyordu — yapısal olarak hiçbir şey
#: yakalayamazdı. Hakem modelinin bağlamı en az 131k token. 60.000 karakter (~20k
#: token), birkaç araç turunu ve tek dosyalık uygulamaların gerçek kodunu taşır.
TRACE_CHARS = 60_000
#: İzde tek bir mesajdan alınacak karakter. 600 karakter yalnız dosyanın başını
#: gösteriyor; davranışı kuran state mutasyonları çoğu kez sonraki bölümde kalıyordu.
TRACE_MESSAGE_CHARS = 16_000
#: Agent'ın nihai cevabından denetçiye gösterilecek kısım.
#:
#: Asılsız "hepsi yapıldı" iddiaları genelde cevabın SONUNDAKİ madde listesindedir;
#: 1.500 karakter o listeyi kesiyordu.
FINAL_TEXT_CHARS = 4_000


#: "TAMAM" ile başlayıp aslında itiraz taşıyan cevaplar ("TAMAM DEĞİL", "Tamam, ama X eksik").
_CLEAN_WITH_OBJECTION = re.compile(
    r"değil|\bama\b|fakat|ancak|\beksik\b|hata var|sorun var", re.IGNORECASE
)
#: Temiz karar anlamına gelen serbest ifadeler: bunlar düzeltme talimatı DEĞİLDİR.
_CLEAN_PHRASES = re.compile(
    r"^\W*(?:sorun yok|bir sorun (?:bulamad|yok)|sorun bulunamad|sorun bulunmuyor|hiçbir sorun"
    r"|hata yok|her şey (?:yolunda|tamam))",
    re.IGNORECASE,
)


def parse_feedback(text: str) -> str:
    """Denetçi çıktısını düzeltme talimatına çevir; sorun yoksa boş metin.

    Ölçüldü (29 Ekim, A4-50): `startswith("TAMAM")` "TAMAM DEĞİL: …" ve "Tamam, ama X
    eksik" cevaplarını temiz sayıp gerçek bir sorunu yutuyordu; "Sorun yok" ise sahte bir
    düzeltme turu açıyordu.
    """
    verdict = (text or "").strip()
    if not verdict or len(verdict) < MIN_INSTRUCTION_CHARS:
        return ""
    if verdict.upper().startswith(CLEAN_VERDICT):
        return "" if _CLEAN_WITH_OBJECTION.search(verdict[:120]) is None else verdict
    if _CLEAN_PHRASES.match(verdict):
        return ""
    return verdict


_PLACEHOLDER = re.compile(r"\{(task|trace|final)\}")


async def review_turn(
    task: str,
    final_text: str,
    messages: list[Message],
    *,
    config: Config,
    publisher: EventPublisher | None = None,
    diff: str = "",
    criteria: tuple[CriterionEvidence, ...] = (),
    failures: tuple[str, ...] = (),
    rate_control: RateControl | None = None,
    task_deadline_s: float | None = None,
) -> str | None:
    """Düzeltme talimatı, açık temiz karar için boş metin, denetim yoksa None döner."""
    trace = history.transcript(messages, TRACE_CHARS, message_chars=TRACE_MESSAGE_CHARS)
    if config.runtime.review_diff_only:
        if not diff.strip():
            return None
        trace = redact(diff)[:DIFF_CHAR_LIMIT] + "\nKriterler:\n" + evidence_text(criteria)
        trace += "\nHatalar:\n" + redact("\n".join(failures))[:FINAL_TEXT_CHARS]
    if not trace.strip() and not final_text.strip():
        return None

    # TEK geçişte doldur: ardışık `.replace` görev/iz içindeki `{final}` gibi metni sonraki
    # yer tutucu sanıp izi bozuyordu (A4-51).
    values = {"task": task, "trace": trace, "final": final_text[:FINAL_TEXT_CHARS]}
    template = await asyncio.to_thread(_PROMPT_PATH.read_text, encoding="utf-8")
    prompt = _PLACEHOLDER.sub(lambda match: values[match.group(1)], template)
    if config.runtime.review_diff_only:
        prompt += (
            "\nYalnız JSON bulgu döndür: path, line (pozitif sayı), reproduction, issue. "
            "Sorun yoksa TAMAM."
        )
    try:
        call = (
            _ask(prompt, config, publisher)
            if rate_control is None and task_deadline_s is None
            else _ask(
                prompt,
                config,
                publisher,
                rate_control=rate_control,
                task_deadline_s=task_deadline_s,
            )
        )
        result = await asyncio.wait_for(call, timeout=config.runtime.judge_timeout_s + 2.0)
    except TimeoutError:
        # Web taşıması istek zaman aşımını her zaman uygulamıyor. Öz-denetim
        # kullanıcının tamamlanmış görevini dakikalarca bekletemez.
        return None
    except Exception:  # sınır: sağlayıcı kurulamadı/çöktü; denetim bir iyileştirmedir (A4-52)
        logging.getLogger(__name__).warning("Öz-denetim yapılamadı", exc_info=True)
        return None
    if not result.ok or result.truncated:
        # Yarım kalmış talimat, hiç talimattan KÖTÜDÜR: agent eksik bir cümleye göre
        # düzeltme yapmaya kalkar. Sıkıştırmadaki "yarım özet" kuralıyla aynı duruş.
        return None
    if not result.text.strip() or (
        len(result.text.strip()) < MIN_INSTRUCTION_CHARS
        and result.text.strip().upper() != CLEAN_VERDICT
    ):
        return None
    if config.runtime.review_diff_only:
        return _diff_feedback(result.text, diff)
    return parse_feedback(result.text)


async def _ask(
    prompt: str,
    config: Config,
    publisher: EventPublisher | None,
    *,
    disable_thinking: bool = False,
    response_schema: Mapping[str, object] | None = None,
    rate_control: RateControl | None = None,
    task_deadline_s: float | None = None,
) -> ModelResult:
    now = SystemClock().monotonic()
    timeout = config.runtime.judge_timeout_s
    if task_deadline_s is not None:
        timeout = min(timeout, task_deadline_s - now)
    if timeout <= 0:
        raise TimeoutError
    structured_nim = (
        response_schema is not None
        and config.judge.model == "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"
    )
    request = CompletionRequest(
        messages=(Message("user", prompt),),
        temperature=config.runtime.utility_temperature,
        max_tokens=config.runtime.judge_max_tokens,
        timeout_s=timeout,
        max_retries=config.runtime.max_retries,
        disable_thinking=disable_thinking and not structured_nim,
        reasoning_effort="medium" if structured_nim else None,
        reasoning_budget=min(_GROUNDED_NIM_REASONING_BUDGET, config.runtime.judge_max_tokens)
        if structured_nim
        else None,
        # Bu model/taşıma eşleşmesinde şema kısıtı gerçek uçta doğrulandı.
        # Diğer denetçiler kendi mevcut metin protokolünü korur.
        response_schema=response_schema if structured_nim else None,
    )
    # Arka plan işi: ilerleme satırı GÖSTERİLMEZ ama harcadığı token muhasebeye girer.
    provider = build_provider(
        config.judge,
        publisher=publisher,
        retry_delays_s=config.runtime.retry_delays_s,
        retry_deadline_s=now + timeout,
        rate_control=rate_control,
        background=True,
        web_sessions=web_registry_for(config),
        model_specs=configured_model_specs(config),
    )
    return await provider.complete(request)


def _diff_feedback(text: str, diff: str) -> str:
    """Konum ve yeniden üretim yoksa otomatik düzeltme başlatma."""
    if not parse_feedback(text):
        return ""
    try:
        finding = json.loads(text)
    except ValueError:
        return ""
    if not isinstance(finding, dict):
        return ""
    path, line = finding.get("path"), finding.get("line")
    paths = {row[6:] for row in diff.splitlines() if row.startswith(("+++ b/", "--- a/"))}
    if not isinstance(path, str) or not path or path not in paths:
        return ""
    if type(line) is not int or line < 1:
        return ""
    if any(
        not isinstance(finding.get(key), str) or not finding[key].strip()
        for key in ("reproduction", "issue")
    ):
        return ""
    return redact(text)

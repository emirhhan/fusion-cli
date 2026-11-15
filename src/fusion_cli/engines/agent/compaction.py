"""Bağlam sıkıştırma — uzun oturumların bağlam limitine çarpmasını önler.

Eski turlar tek bir özet notuna indirilir, son turlar birebir korunur. Özet
üretilemezse geçmiş DEĞİŞTİRİLMEZ: yarım bir özet, hiç özetten kötüdür.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from ...config.model_lookup import configured_model_specs
from ...config.models import Config
from ...core.errors import ConfigError, ProviderError
from ...core.events import EventPublisher
from ...core.original_trace import OriginalTraceReader, OriginalTraceScope
from ...core.types import CompletionRequest, Message
from ...providers.factory import build_provider
from ...providers.web_browser import WebBrowserError
from ...providers.web_registry import web_registry_for
from . import history
from .research_evidence import bounded_evidence, can_bound_evidence

_LOG = logging.getLogger(__name__)

_PROMPT = (Path(__file__).parent / "prompts" / "compress.txt").read_text(encoding="utf-8")

#: Özet çağrısının DIŞ süre sınırı (saniye).
#:
#: Ölçüldü (30 Ekim, gerçek kullanım): iş bitmiş, cevap basılmıştı; tur sonu bağlam
#: özeti web modeline gitti ve model hiç dönmedi. İstek zaman aşımı (`request_timeout_s`,
#: 600 sn) web taşımasında her zaman uygulanmıyor ve uygulansa bile on dakikadır; tur
#: 20 dakika boyunca tek satır çıktı basmadan asılı kaldı. Özet bir iyileştirmedir
#: (üretilemezse geçmiş değişmez), kullanıcının bitmiş turunu bekletemez. Öğrenmenin
#: sınırıyla (`learning_steps.LEARN_TIMEOUT_S`) aynı büyüklük.
SUMMARY_TIMEOUT_S = 120.0
#: Özet için ayrılan token bütçesi.
#:
#: Sıkıştırma eşiği yükseldiği için özetlenen geçmiş de büyüdü; 600 token artık atılan
#: içeriği temsil edemezdi.
SUMMARY_MAX_TOKENS = 2_000
#: Özetleyiciye verilecek oturum izinin uzunluğu.
#:
#: Eskiden 6.000 karakterdi. Eşik 177.000 karaktere çıkınca özetleyici, attığı geçmişin
#: ancak %3'ünü görüyor olurdu — özet yalnızca gördüğü kadarını temsil eder.
TRACE_CHARS = 60_000
#: İz içinde bir mesaja tanınan pay aralığı (karakter).
TRACE_MESSAGE_MIN_CHARS = history.TRACE_MESSAGE_CHARS
TRACE_MESSAGE_MAX_CHARS = 2_000
#: Özetlenen aralıktan birebir taşınan kullanıcı kurallarının üst sınırı.
RULES_MAX_CHARS = 2_000
#: Özete eklenen kural bloğunun başlığı; art arda sıkıştırmada blok yeniden taşınır.
RULES_HEADER = "[kullanıcının koyduğu kurallar — birebir]"

#: Kullanıcının kalıcı kural koyduğunu gösteren ifadeler (yasak, sınır, süreklilik).
_RULE_PATTERN = re.compile(
    r"\b(?:asla|sakın|hiçbir zaman|her zaman|bundan sonra|mutlaka|yasak|izin verme|"
    r"sadece|yalnızca|yapma|etme|dokunma|değiştirme|silme|kullanma|kurma|yükleme|"
    r"gönderme|pushlama|commitleme|never|always|only|don't|do not)\b",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def trace_message_chars(old: list[Message]) -> int:
    """Mesaj başına iz payı: toplam bütçeyi mesaj sayısına böl, aralığa sıkıştır.

    Sabit 300 karakter, 177 K karakterlik geçmişi 60 K'lık ize ~300 karakter/mesaj
    sadakatiyle indiriyordu; az mesajlı ama büyük çıktılı geçmişte bütçe boşa kalıyordu
    (A1-02, ölçüldü 29 Ekim).
    """
    pay = TRACE_CHARS // max(1, len(old))
    return max(TRACE_MESSAGE_MIN_CHARS, min(TRACE_MESSAGE_MAX_CHARS, pay))


async def compress(
    messages: list[Message],
    *,
    config: Config,
    publisher: EventPublisher | None = None,
    threshold_chars: int | None = None,
    original_source: OriginalTraceReader | None = None,
    original_scope: OriginalTraceScope | None = None,
    pinned_call_ids: frozenset[str] = frozenset(),
    manual: bool = False,
    focus: str = "",
) -> list[Message]:
    """Geçmiş eşiği aştıysa eski kısmı özetle. Aksi halde aynen döndür.

    `manual` (elle `/compact`, #186): Claude Code gibi eşik denetimi atlanır ve kök tur
    dışındaki bütün konuşma özetlenir. `focus` özet istemine odak talimatı olarak eklenir.
    """
    if not manual and not history.needs_compression(messages, threshold_chars=threshold_chars):
        return messages

    cut = len(messages) if manual else history.safe_cut(messages)
    if cut == 0:
        return messages

    # Kök tur (sistem mesajı + ilk kullanıcı sorusu) özetleyiciye asla verilmez.
    # Ölçüldü ("MAVİ-KEDİ" vakası): kesim sistem mesajını ve kullanıcının kök
    # turda söylediği talimatı da `old`'a alıyor, özetleyici o ayrıntıyı hiç
    # yazmayabiliyordu — bilgi telafisiz kayboluyordu. Kök tur burada anchor
    # olarak ayrılır ve `recent` gibi BİREBİR korunur.
    anchor_len = history.root_anchor_length(messages)
    anchor, old, recent = messages[:anchor_len], messages[anchor_len:cut], messages[cut:]
    if not old or not can_bound_evidence(old):
        return messages
    source_messages, provenance = await _original_messages(
        old, recent, original_source, original_scope
    )
    trace = history.transcript(
        source_messages, limit=TRACE_CHARS, message_chars=trace_message_chars(source_messages)
    )
    if provenance:
        trace = f"{provenance}\n{trace}"
    if not trace.strip():
        return messages

    summary = await _summarize(trace, config, publisher, focus=focus)
    if not summary:
        return messages
    summary = _with_user_rules(summary, old)
    # `harness_note`: bu bir kullanıcı görevi DEĞİL. Eksikken "devam et" sonrası
    # `task_effect` özet metnini en son gerçek görev sanıyordu (A1-03).
    ozet = Message("user", f"{history.CONVERSATION_SUMMARY_PREFIX}\n{summary}", harness_note=True)
    return [*anchor, ozet, *_user_updates(old), *_pinned_messages(old, pinned_call_ids), *recent]


async def compact_in_turn(
    messages: list[Message],
    *,
    config: Config,
    publisher: EventPublisher | None = None,
    threshold_chars: int,
    original_source: OriginalTraceReader | None = None,
    original_scope: OriginalTraceScope | None = None,
    pinned_call_ids: frozenset[str] = frozenset(),
) -> list[Message]:
    """Tur SÜRERKEN bağlamı eşiğin altına indir: önce eski çıktılar, sonra özet.

    Claude Code'un belgelenmiş sırası: "önce eski araç çıktılarını temizler,
    gerekirse sonra konuşmayı özetler; istekleriniz ve önemli kod parçaları
    korunur". Sistem mesajı ve görev (`task_anchor_length`) hiç özetlenmez.
    Özet üretilemezse yalnız temizlenmiş liste döner.
    """
    if not history.needs_compression(messages, threshold_chars=threshold_chars):
        return messages
    if not can_bound_evidence(messages):
        _LOG.warning("Kaynak kimlikleri kanıt bütçesine sığmıyor; özgün geçmiş korundu.")
        return messages
    temiz = history.clear_old_tool_outputs(
        messages, threshold_chars, pinned_call_ids=pinned_call_ids
    )
    if not history.needs_compression(temiz, threshold_chars=threshold_chars):
        return temiz
    anchor_len = history.task_anchor_length(temiz)
    cut = _summary_cut(temiz, anchor_len)
    if cut <= anchor_len:
        return temiz
    anchor, old, recent = temiz[:anchor_len], temiz[anchor_len:cut], temiz[cut:]
    source_messages, provenance = await _original_messages(
        messages[anchor_len:cut], messages[cut:], original_source, original_scope
    )
    trace = history.transcript(
        source_messages, limit=TRACE_CHARS, message_chars=trace_message_chars(source_messages)
    )
    if provenance:
        trace = f"{provenance}\n{trace}"
    if not trace.strip():
        return temiz
    summary = await _summarize(trace, config, publisher)
    if not summary:
        return temiz
    summary = _with_user_rules(summary, [*old, *source_messages])
    ozet = Message("user", f"{history.STEPS_SUMMARY_PREFIX}\n{summary}", harness_note=True)
    retained = _pinned_messages(old, pinned_call_ids)
    return [*anchor, ozet, *_user_updates(old), *retained, *recent]


def _pinned_messages(messages: list[Message], identities: frozenset[str]) -> list[Message]:
    """Seçili kanıtın çağrı/sonuç çiftini sınırlı tut; ikinci iz deposu kurma."""
    from dataclasses import replace

    retained: list[Message] = []
    evidence = bounded_evidence(messages)
    evidence_ids = {message.tool_call_id for message in evidence.values()}
    for index, message in enumerate(messages):
        if message.role == "assistant":
            calls = tuple(
                call
                if call.id in evidence_ids
                else replace(call, arguments=history._stub_arguments(call.arguments))
                for call in message.tool_calls
                if call.id in identities or call.id in evidence_ids
            )
            if calls:
                retained.append(replace(message, content="", tool_calls=calls))
        elif index in evidence:
            retained.append(evidence[index])
        elif message.role == "tool" and message.tool_call_id in identities:
            retained.append(history.pin_tool_output(message))
    return retained


def _user_updates(messages: list[Message]) -> list[Message]:
    """Ara kullanıcı talimatları olasılıksal özete emanet edilmez; birebir taşınır."""
    return [message for message in messages if message.role == "user" and not message.harness_note]


async def _original_messages(
    old: list[Message],
    recent: list[Message],
    source: OriginalTraceReader | None,
    scope: OriginalTraceScope | None,
) -> tuple[list[Message], str]:
    """Doğrulanmış kaynağı gerçekten oku; eksik iz yerine özeti özgün diye sunma."""
    if source is None and scope is None:
        return old, ""
    status = "invalid_scope"
    if source is not None and scope is not None and scope.is_valid():
        try:
            result = await source.read_original(scope)
            status = result.status
            originals = list(result.messages)
            if (
                result.is_usable()
                and result.scope == scope
                and _matches_original_scope(originals, old, recent, scope)
            ):
                return originals, "[kaynak: maskelenmiş özgün segment; iz örneklenebilir]"
            if status == "redacted_original":
                status = "incomplete"
        except (OSError, ValueError) as error:
            status = "unavailable"
            _LOG.warning("özgün iz kaynağı okunamadı", extra={"hata": type(error).__name__})
    _LOG.info("özgün iz kullanılamadı; sıkıştırılmış geçmiş kullanılıyor", extra={"durum": status})
    return old, f"[kaynak: sıkıştırılmış geçmiş; özgün iz kullanılamadı ({status})]"


def _matches_original_scope(
    originals: list[Message],
    old: list[Message],
    recent: list[Message],
    scope: OriginalTraceScope,
) -> bool:
    """Kaynak bütçeyi aşamaz, özet içeremez veya son araç grubunu yeniden özetleyemez."""
    if not originals or history.total_chars(originals) > scope.max_chars:
        return False
    if any(message.harness_note or history.is_summary_message(message) for message in originals):
        return False
    original_calls = {call.id for message in originals for call in message.tool_calls}
    old_calls = {call.id for message in old for call in message.tool_calls}
    recent_calls = {call.id for message in recent for call in message.tool_calls}
    return old_calls <= original_calls and not original_calls & recent_calls


def _with_user_rules(summary: str, old: list[Message]) -> str:
    """Özetlenen aralıktaki kullanıcı kurallarını özete BİREBİR ekle.

    Kuralın kalıcılığı özetleyici modelin özenine bırakılmaz: zayıf bir özetleyici
    "main'e asla push etme" cümlesini düşürürse ajan yasağı unutur.
    """
    rules = _user_rules(old)
    if not rules:
        return summary
    return f"{summary}\n\n{RULES_HEADER}\n" + "\n".join(f"- {rule}" for rule in rules)


def _user_rules(messages: list[Message]) -> list[str]:
    found: list[str] = []
    total = 0
    for message in messages:
        # Harness notları ("pes etme" vb.) kullanıcının kuralı değildir. İstisna: önceki
        # sıkıştırmanın özeti (artık `harness_note`) taşıdığı kural bloğuyla birlikte
        # yeniden taşınır; yoksa ikinci sıkıştırmada kurallar düşerdi.
        if message.role != "user" or (message.harness_note and RULES_HEADER not in message.content):
            continue
        for sentence in _rule_sentences(message.content):
            if sentence in found or total + len(sentence) > RULES_MAX_CHARS:
                continue
            found.append(sentence)
            total += len(sentence)
    return found


def _rule_sentences(content: str) -> list[str]:
    if RULES_HEADER in content:
        # Önceki özetin kural bloğu: maddeler olduğu gibi yeniden taşınır.
        block = content.split(RULES_HEADER, 1)[1]
        return [line[2:].strip() for line in block.splitlines() if line.startswith("- ")]
    return [
        sentence.strip()
        for sentence in _SENTENCE_END.split(content)
        # Soru cümlesi ("hep mi bozuluyor?") kural koymaz.
        if sentence.strip()
        and not sentence.strip().endswith("?")
        and _RULE_PATTERN.search(sentence)
    ]


def _summary_cut(messages: list[Message], anchor_len: int) -> int:
    """Özetlenecek aralığın sonu: olabildiğince çok son adımı koru, ama bir şey özetle.

    Önce olağan pencere (`KEEP_RECENT_MESSAGES`) denenir; tur kısa ama çıktıları
    büyükse pencere daraltılır. En az son araç turu (çağrı + sonuç) birebir kalır.
    """
    pencere = history.KEEP_RECENT_MESSAGES
    while pencere >= 2:
        cut = history.round_cut(messages, keep_recent=pencere)
        if cut > anchor_len:
            return cut
        pencere //= 2
    return 0


def summary_timeout_s(config: Config) -> float:
    """Özet çağrısı için bekleme sınırı: istek zaman aşımından uzun olamaz."""
    return min(config.runtime.request_timeout_s, SUMMARY_TIMEOUT_S)


#: Elle `/compact <talimat>` odağının özet istemine eklenen başlığı (#186).
FOCUS_HEADER = "Odak talimatı (kullanıcı /compact ile verdi; özeti buna göre kur):"


def summary_prompt(trace: str, focus: str = "") -> str:
    """Özet istemi; `focus` doluysa izden önce odak talimatı eklenir."""
    prompt = _PROMPT.replace("{trace}", trace)
    cleaned = focus.strip()
    if not cleaned:
        return prompt
    return f"{FOCUS_HEADER}\n{cleaned}\n\n{prompt}"


async def _summarize(
    trace: str, config: Config, publisher: EventPublisher | None, *, focus: str = ""
) -> str:
    request = CompletionRequest(
        messages=(Message("user", summary_prompt(trace, focus)),),
        temperature=config.runtime.utility_temperature,
        max_tokens=SUMMARY_MAX_TOKENS,
        timeout_s=config.runtime.request_timeout_s,
        max_retries=config.runtime.max_retries,
    )
    # Arka plan işi: gösterilmez ama muhasebeye girer.
    # Ölçüldü (30 Ekim, A1-34): sağlayıcı kurulamaz (judge tanımsız) ya da çağrı
    # istisna fırlatırsa sıkıştırma turu düşürüyordu; docstring "özet üretilemezse
    # geçmiş değişmez" der. İstisna da "özet yok" sayılır.
    try:
        provider = build_provider(
            config.judge,
            publisher=publisher,
            retry_delays_s=config.runtime.retry_delays_s,
            background=True,
            web_sessions=web_registry_for(config),
            model_specs=configured_model_specs(config),
        )
        async with asyncio.timeout(summary_timeout_s(config)):
            result = await provider.complete(request)
    except TimeoutError:
        # Web taşıması sağlayıcı zaman aşımını her zaman uygulamıyor; geçmiş değişmez.
        _LOG.info("Bağlam özeti %.0f saniyede gelmedi, atlandı", summary_timeout_s(config))
        return ""
    except (ConfigError, ProviderError, WebBrowserError, OSError) as error:
        _LOG.warning("Bağlam özeti üretilemedi: %s", error)
        return ""
    return result.text.strip() if result.ok else ""

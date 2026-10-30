"""Bağlam sıkıştırma — uzun oturumların bağlam limitine çarpmasını önler.

Eski turlar tek bir özet notuna indirilir, son turlar birebir korunur. Özet
üretilemezse geçmiş DEĞİŞTİRİLMEZ: yarım bir özet, hiç özetten kötüdür.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from ...config.models import Config
from ...core.errors import ConfigError, ProviderError
from ...core.events import EventPublisher
from ...core.types import CompletionRequest, Message
from ...providers.factory import build_provider
from ...providers.web_browser import WebBrowserError
from ...providers.web_registry import web_registry_for
from . import history

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
) -> list[Message]:
    """Geçmiş eşiği aştıysa eski kısmı özetle. Aksi halde aynen döndür."""
    if not history.needs_compression(messages, threshold_chars=threshold_chars):
        return messages

    cut = history.safe_cut(messages)
    if cut == 0:
        return messages

    # Kök tur (sistem mesajı + ilk kullanıcı sorusu) özetleyiciye asla verilmez.
    # Ölçüldü ("MAVİ-KEDİ" vakası): kesim sistem mesajını ve kullanıcının kök
    # turda söylediği talimatı da `old`'a alıyor, özetleyici o ayrıntıyı hiç
    # yazmayabiliyordu — bilgi telafisiz kayboluyordu. Kök tur burada anchor
    # olarak ayrılır ve `recent` gibi BİREBİR korunur.
    anchor_len = history.root_anchor_length(messages)
    anchor, old, recent = messages[:anchor_len], messages[anchor_len:cut], messages[cut:]
    if not old:
        return messages
    trace = history.transcript(old, limit=TRACE_CHARS, message_chars=trace_message_chars(old))
    if not trace.strip():
        return messages

    summary = await _summarize(trace, config, publisher)
    if not summary:
        return messages
    summary = _with_user_rules(summary, old)
    # `harness_note`: bu bir kullanıcı görevi DEĞİL. Eksikken "devam et" sonrası
    # `task_effect` özet metnini en son gerçek görev sanıyordu (A1-03).
    ozet = Message("user", f"{history.CONVERSATION_SUMMARY_PREFIX}\n{summary}", harness_note=True)
    return [*anchor, ozet, *recent]


async def compact_in_turn(
    messages: list[Message],
    *,
    config: Config,
    publisher: EventPublisher | None = None,
    threshold_chars: int,
) -> list[Message]:
    """Tur SÜRERKEN bağlamı eşiğin altına indir: önce eski çıktılar, sonra özet.

    Claude Code'un belgelenmiş sırası: "önce eski araç çıktılarını temizler,
    gerekirse sonra konuşmayı özetler; istekleriniz ve önemli kod parçaları
    korunur". Sistem mesajı ve görev (`task_anchor_length`) hiç özetlenmez.
    Özet üretilemezse yalnız temizlenmiş liste döner.
    """
    if not history.needs_compression(messages, threshold_chars=threshold_chars):
        return messages
    temiz = history.clear_old_tool_outputs(messages, threshold_chars)
    if not history.needs_compression(temiz, threshold_chars=threshold_chars):
        return temiz
    anchor_len = history.task_anchor_length(temiz)
    cut = _summary_cut(temiz, anchor_len)
    if cut <= anchor_len:
        return temiz
    anchor, old, recent = temiz[:anchor_len], temiz[anchor_len:cut], temiz[cut:]
    trace = history.transcript(old, limit=TRACE_CHARS, message_chars=trace_message_chars(old))
    if not trace.strip():
        return temiz
    summary = await _summarize(trace, config, publisher)
    if not summary:
        return temiz
    summary = _with_user_rules(summary, old)
    ozet = Message("user", f"{history.STEPS_SUMMARY_PREFIX}\n{summary}", harness_note=True)
    return [*anchor, ozet, *recent]


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


async def _summarize(trace: str, config: Config, publisher: EventPublisher | None) -> str:
    request = CompletionRequest(
        messages=(Message("user", _PROMPT.replace("{trace}", trace)),),
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

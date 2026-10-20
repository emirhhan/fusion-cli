"""LiteLLM adaptörü — tek bir modele çağrı yapar.

Sorumluluğu dardır ve bilinçlidir: SDK'yı çağırır, yanıtı `ModelResult`/`StreamItem`
tiplerine normalize eder. Yeniden deneme, yedeğe geçme ve olay yayını burada DEĞİL, üstteki
dekoratörlerdedir (`retrying.py`, `chain.py`, `eventing.py`). Böylece yeni bir sağlayıcı eklemek
yalnızca bu dosyanın bir eşdeğerini yazmak olur; dayanıklılık davranışı bedava gelir.

LiteLLM 100+ sağlayıcıyı model kimliğinin "<sağlayıcı>/<model>" önekinden tanır;
ayrı bir proxy sunucusu çalıştırmaya gerek yoktur.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from ..core.clock import SystemClock
from ..core.model_capability import ModelCapability
from ..core.protocols import Clock
from ..core.reasoning import resolve_reasoning
from ..core.redaction import redact
from ..core.tool_emulation import CALL_CLOSE, CALL_OPEN, parse_tool_calls
from ..core.types import (
    CompletionRequest,
    Message,
    ModelResult,
    StreamDone,
    StreamItem,
    TextChunk,
    TokenUsage,
    ToolCall,
)
from .context_window import OLLAMA_NUM_CTX

#: NVIDIA NIM anahtarı varken taban adres verilmemişse kullanılacak varsayılan uç.
NIM_DEFAULT_API_BASE = "https://integrate.api.nvidia.com/v1"

#: Çıktı bütçesi düşünme sırasında dolduğunda kullanıcıya dönen açıklama.
TRUNCATED_ERROR = (
    "Model çıktı bütçesi dolduğu için cevabı üretemedi (yalnızca düşünme aşaması "
    "tamamlandı). `runtime.max_tokens` değerini artır."
)

#: Sağlayıcılar düşünme metnini farklı alan adlarıyla döndürür.
_REASONING_FIELDS = ("reasoning_content", "reasoning")

_logger = logging.getLogger(__name__)


def _litellm() -> Any:  # litellm modülü; tip stub'ı yok, SDK sınırında Any kaçınılmaz.
    """LiteLLM'i tembel yükle ve döndür.

    `litellm` import'u ~1.6s sürer ve CLI'ın soğuk açılışının neredeyse tamamıdır;
    modül tepesinde import edilirse `--help`/`--version`/`setup` gibi LLM'e hiç
    dokunmayan yollar da bu bedeli öder. chromadb ile aynı disiplin: gerçekten
    çağrı yapıldığı anda yüklenir. Python import önbelleği tekrar yüklemeyi önler.
    """
    import litellm

    return litellm


def configure_litellm() -> None:
    """LiteLLM'i bir kez ayarla. Import anında değil, açık çağrıyla yapılır."""
    litellm = _litellm()
    litellm.suppress_debug_info = True
    # Sağlayıcının desteklemediği parametreleri sessizce at (ör. bazı uçlarda temperature).
    litellm.drop_params = True
    if os.getenv("NVIDIA_NIM_API_KEY") and not os.getenv("NVIDIA_NIM_API_BASE"):
        os.environ["NVIDIA_NIM_API_BASE"] = NIM_DEFAULT_API_BASE


class LiteLlmProvider:
    """Tek bir model kimliğine bağlı sağlayıcı."""

    def __init__(
        self,
        model: str,
        *,
        role: str,
        clock: Clock | None = None,
        api_key: str | None = None,
        capability: ModelCapability | None = None,
    ) -> None:
        self._model = model
        self._capability = capability or ModelCapability()
        self._role = role
        self._clock = clock or SystemClock()
        #: Verilirse bu çağrıda ortam değişkeni yerine bu anahtar kullanılır (çok-hesap
        #: havuzu). None ise LiteLLM ilgili sağlayıcının ortam değişkenini okur.
        self._api_key = api_key

    @property
    def label(self) -> str:
        return self._model

    async def complete(self, request: CompletionRequest) -> ModelResult:
        started = self._clock.monotonic()
        try:
            response = await _litellm().acompletion(**self._call_kwargs(request, stream=False))
        except Exception as exc:
            # Sağlayıcı hataları BEKLENEN durumdur (429, 5xx, zaman aşımı, soğuk uç):
            # akışı kesmemek için exception'a değil sonuç nesnesine çevrilir.
            return self._with_effort(self._failure(exc, started), request)
        return self._with_effort(self._success(response, started), request)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        started = self._clock.monotonic()
        chunks: list[Any] = []
        try:
            response = await _litellm().acompletion(**self._call_kwargs(request, stream=True))
            async for chunk in response:
                chunks.append(chunk)
                text = _chunk_text(chunk)
                if text:
                    yield TextChunk(text)
                else:
                    # Araç argümanı ya da düşünme parçası: metin yok ama model
                    # ÇALIŞIYOR. Ölçüldü (29 Eylül): uzun bir dosyayı araç argümanı
                    # olarak yazan model iki dakika "sessiz" sanılıp her denemede
                    # kesildi. Boş, geçici parça ekrana metin düşürmez; yalnız
                    # sessizlik sınırını tazeler (bkz. `loop._call_model`).
                    yield TextChunk("", provisional=True)
        except Exception as exc:
            yield StreamDone(self._with_effort(self._failure(exc, started), request))
            return
        yield StreamDone(self._with_effort(self._rebuild(chunks, request, started), request))

    # ----------------------------------------------------------------------- #

    def _call_kwargs(self, request: CompletionRequest, *, stream: bool) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [_to_wire(message) for message in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout": request.timeout_s,
            "num_retries": request.max_retries,
        }
        if request.tools:
            kwargs["tools"] = [dict(schema) for schema in request.tools]
            kwargs["tool_choice"] = "auto"
            # Nemotron 3'e `force_nonempty_content` GÖNDERİLMEZ. Ölçüldü (27 Eylül,
            # 6/6 deneme): bu şablon seçeneği düşünme metnini `reasoning_content`
            # yerine cevaba döküyor, çoğu zaman `</think>` ile, bazen yarıda kesilip
            # işaretsiz; kullanıcı iki cevabı arka arkaya gördü. Seçeneksiz 6/6 araç
            # çağrısı doğru ayrıştı ve boş içerikli araç turu geçmişte sorunsuz döndü.
        if self._api_key is not None:
            # Havuzdan gelen anahtar ortam değişkenini geçersiz kılar (çok-hesap).
            kwargs["api_key"] = self._api_key
        resolution = resolve_reasoning(request.reasoning_effort, self._capability)
        if resolution.applied is not None:
            kwargs["reasoning_effort"] = resolution.applied
        if request.disable_thinking and self._model.startswith(_TEMPLATE_THINKING_PREFIXES):
            # Yalnız ölçülen sağlayıcıda: NIM şablon anahtarı. Başka uçlara ham gövde
            # gönderilmez (OpenAI 400 verir).
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        measured_local_default = self._model in {
            "ollama/huihui_ai/qwen3.5-abliterated:9b",
            "ollama_chat/huihui_ai/qwen3.5-abliterated:9b",
        } and request.reasoning_effort in (None, "auto")
        # Measured on the local 9B: even a greeting exhausted 512 tokens in
        # thinking. Keep the default usable; an explicit effort opts back in.
        if self._model.startswith(("ollama/", "ollama_chat/")) and (
            request.disable_thinking or measured_local_default
        ):
            kwargs["think"] = False
        if self._model.startswith(("ollama/", "ollama_chat/")):
            # Ollama bağlamı varsayılanda 4096 token'da tutar (18 Ekim 2026'da
            # `/api/ps` ile ölçüldü: context_length 4096). Fusion'ın sistem istemi ve
            # araç şemaları tek başına bunu aşıyor; Ollama en eski mesajları, yani
            # SİSTEM İSTEMİNİ, sessizce kesiyordu. Model araç sözleşmesini görmeden
            # tekrar döngüsüne giriyor ve görevleri hiç bitiremiyordu.
            kwargs["num_ctx"] = OLLAMA_NUM_CTX
            # Ollama boştaki modeli 5 dakikada boşaltır; ~16k token'lık sistem istemi
            # yeniden işlenince ilk yanıt ~4 dakika sürüyor (18 Ekim izinde 228 sn;
            # önbellekli turlar ~20 sn). Model yüklü kalsın.
            kwargs.setdefault("keep_alive", "60m")
            # Qwen'in önerdiği örnekleme (düşünmesiz mod); düşük sıcaklıkta tekrar
            # döngüsüne girmesini cezayla kırar.
            kwargs.setdefault("top_k", 20)
            kwargs.setdefault("top_p", 0.8)
            kwargs.setdefault("repeat_penalty", 1.1)
        if stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
        return kwargs

    def _with_effort(self, result: ModelResult, request: CompletionRequest) -> ModelResult:
        resolution = resolve_reasoning(request.reasoning_effort, self._capability)
        return replace(
            result,
            requested_effort=resolution.requested,
            applied_effort=resolution.applied,
            effort_reason=resolution.reason,
        )

    def _elapsed_ms(self, started: float) -> int:
        return int((self._clock.monotonic() - started) * 1000)

    def _failure(self, exc: Exception, started: float) -> ModelResult:
        # httpx/litellm istisna metni bazen istek URL'ini veya Authorization
        # header'ını (API anahtarı) içerir; hata yukarı akmadan önce redakte edilir.
        return ModelResult(
            name=self._role,
            model=self._model,
            text="",
            latency_ms=self._elapsed_ms(started),
            ok=False,
            error=redact(f"{type(exc).__name__}: {exc}"),
        )

    def _success(self, response: Any, started: float) -> ModelResult:
        text = _response_text(response)
        tool_calls = _response_tool_calls(response)
        # Reasoning modelinde düşünme token'ları da çıktı bütçesinden yenir. Bütçe
        # düşünme sırasında dolarsa `content` BOŞ gelir ve tur sessizce boş cevapla
        # biter — kullanıcı bunu "hiçbir şey yapmadı" diye görür. Bu bir başarı
        # değildir; açık hataya çevrilir ki yedek zinciri devreye girebilsin.
        yarim = _finish_reason(response) == "length"
        kesildi = yarim and not text and not tool_calls
        return ModelResult(
            name=self._role,
            model=self._model,
            text=text,
            latency_ms=self._elapsed_ms(started),
            ok=not kesildi,
            error=TRUNCATED_ERROR if kesildi else None,
            usage=_response_usage(response, self._model),
            tool_calls=tool_calls,
            reasoning=_response_reasoning(response),
            truncated=yarim,
            served_by=_observed_model(response),
        )

    def _rebuild(
        self, chunks: list[Any], request: CompletionRequest, started: float
    ) -> ModelResult:
        """Akış parçalarını tek yanıta toparla; toparlanamazsa metni parçalardan birleştir."""
        try:
            rebuilt = _litellm().stream_chunk_builder(
                chunks,
                messages=[_to_wire(message) for message in request.messages],
            )
        except Exception:
            rebuilt = None
        akis_reasoning = "".join(_chunk_reasoning(chunk) for chunk in chunks)
        if rebuilt is None:
            return ModelResult(
                name=self._role,
                model=self._model,
                text="".join(_chunk_text(chunk) for chunk in chunks),
                latency_ms=self._elapsed_ms(started),
                ok=True,
                reasoning=akis_reasoning,
                served_by=next(
                    (
                        _observed_model(chunk)
                        for chunk in reversed(chunks)
                        if _observed_model(chunk)
                    ),
                    "",
                ),
            )
        sonuc = self._success(rebuilt, started)
        if not sonuc.served_by:
            observed = next(
                (_observed_model(chunk) for chunk in reversed(chunks) if _observed_model(chunk)), ""
            )
            sonuc = replace(sonuc, served_by=observed)
        if sonuc.reasoning or not akis_reasoning:
            return sonuc
        # `stream_chunk_builder` düşünme metnini her sağlayıcıda taşımaz; parçalardan
        # topladığımız metin varsa kaybedilmez.
        return replace(sonuc, reasoning=akis_reasoning)


# --------------------------------------------------------------------------- #
# SDK nesnelerini okuma — bu sınır dışına LiteLLM tipi sızmaz.
# --------------------------------------------------------------------------- #


def _observed_model(response: Any) -> str:
    """Gerçek yanıt kimliği yoksa boş kalır; istenen model gözlem değildir."""
    value = getattr(response, "model", None)
    return value.strip() if isinstance(value, str) else ""


def _response_text(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        return ""
    return str(content or "").strip()


def _response_reasoning(response: Any) -> str:
    """Reasoning modelinin düşünme metni. Alan adı sağlayıcıya göre değişir."""
    try:
        message = response.choices[0].message
    except (AttributeError, IndexError, TypeError):
        return ""
    return _first_field(message, _REASONING_FIELDS)


def _finish_reason(response: Any) -> str:
    """Yanıtın neden bittiği. Bilinmiyorsa boş dizge."""
    try:
        return str(response.choices[0].finish_reason or "")
    except (AttributeError, IndexError, TypeError):
        return ""


def _first_field(source: Any, fields: tuple[str, ...]) -> str:
    """Verilen alanlardan ilk dolu olanı dizge olarak döndür."""
    for field in fields:
        value = getattr(source, field, None)
        if value:
            return str(value)
    return ""


def _response_usage(response: Any, model: str) -> TokenUsage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return TokenUsage()
    prompt_value = getattr(usage, "prompt_tokens", None)
    completion_value = getattr(usage, "completion_tokens", None)
    prompt_tokens = int(prompt_value or 0)
    completion_tokens = int(completion_value or 0)
    cost = _estimated_cost(model, prompt_tokens, completion_tokens)
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost or 0.0,
        prompt_measured=prompt_value is not None,
        completion_measured=completion_value is not None,
        cost_known=cost is not None and prompt_value is not None and completion_value is not None,
    )


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Eski sayısal arayüz; bilinmeyen fiyat metadata içinde ayrıca belirtilir."""
    return _estimated_cost(model, prompt_tokens, completion_tokens) or 0.0


def _estimated_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    """Sağlayıcı fiyatı yoksa maliyeti bilinmiyor olarak taşı."""
    try:
        cost = _litellm().completion_cost(
            completion_response={
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            },
            model=model,
        )
    # Geniş yakalama bilinçli: litellm bilinmeyen/yerel modelde çeşitli istisna
    # tipleri fırlatabilir. Maliyet 0'a düşer ama SESSİZ değil — teşhis için loglanır.
    except Exception as exc:
        _logger.debug("Maliyet hesaplanamadı (%s).", type(exc).__name__)
        return None
    return float(cost) if cost is not None else None


def _response_tool_calls(response: Any) -> tuple[ToolCall, ...]:
    """SDK yanıtındaki araç çağrılarını proje tipine çevir."""
    try:
        raw = response.choices[0].message.tool_calls
    except (AttributeError, IndexError, TypeError):
        return ()
    if not raw:
        return ()
    calls: list[ToolCall] = []
    for item in raw:
        try:
            call_id = str(item.id)
            name = str(item.function.name)
            arguments = str(item.function.arguments or "{}")
        except AttributeError:
            continue
        name, arguments = _unwrap_emulation_leak(name, arguments)
        calls.append(ToolCall(id=call_id, name=name, arguments=arguments))
    return tuple(calls)


def _unwrap_emulation_leak(name: str, arguments: str) -> tuple[str, str]:
    """Taklit protokolü sınırlayıcısı yerleşik çağrının ADI olarak sızarsa onar.

    Ölçüldü (masaüstü uygulaması, API modeli nvidia_nim/nemotron — yerleşik
    (native) araç çağrısı yapan bir model): bir turdaki `ToolExecuted` olayının
    araç adı `FUSION_TOOL_CALL` çıktı. Bu, metin tabanlı taklit protokolünün
    (`core/tool_emulation.py`) sınırlayıcısıdır; model onu native çağrının
    fonksiyon ADI olarak göndermiş, GERÇEK çağrıyı (`{"name": …, "arguments": …}`)
    argüman gövdesine yazmıştı.

    Bunu bilinmeyen araç sayıp modele bir onarım turu harcatmak (kayıt defteri
    zaten "bilinmeyen araç" hatasını üretebiliyorken) niyet AÇIKÇA belliyken
    israftır — tıpkı `tools/builtin.py::_ALIASES` tahminlerinde olduğu gibi.
    Gövde zaten taklit protokolünün kendi sözdizimidir; ikinci bir ayrıştırıcı
    açmak yerine `parse_tool_calls` ile çözülüp GERÇEK çağrı çalıştırılır.

    Sınırlayıcı adla eşleşmiyorsa ya da gövde ayrıştırılamıyorsa isim/argüman
    OLDUĞU GİBİ döner; sözleşme denetimi bunu normal şekilde "bilinmeyen araç"
    olarak raporlar.
    """
    if name not in (CALL_OPEN, CALL_CLOSE):
        return name, arguments
    parsed = parse_tool_calls(f"{CALL_OPEN}\n{arguments}\n{CALL_CLOSE}")
    if not parsed.calls:
        return name, arguments
    real = parsed.calls[0]
    return real.name, real.arguments


#: Şablon düzeyinde düşünme anahtarını (`chat_template_kwargs.enable_thinking`) tanıyan
#: sağlayıcı önekleri. Ölçüldü (3 Ekim 2026, NIM Nemotron 3 Ultra): anahtar kapalıyken
#: düşünme metni 0, araç çağrısı geçerli, süre 161 sn → 29 sn.
_TEMPLATE_THINKING_PREFIXES = ("nvidia_nim/",)


def _valid_arguments(raw: str) -> str:
    """Araç argümanlarını GEÇERLİ JSON metnine indir.

    Modelin bozuk ürettiği argüman (ör. geçerli nesnenin arkasında artık veri) geçmişte
    olduğu gibi kalırsa, SONRAKİ her istekte LiteLLM'in Ollama dönüştürücüsü
    `json.loads` ile patlıyordu ("Extra data"): tek bozuk çağrı turu öldürüyor, 10 kez
    60 sn beklenip yeniden deneniyordu (18 Ekim 2026, soak koşuları). İlk tam nesne
    korunur; hiç okunamazsa boş nesne gönderilir.
    """
    try:
        json.loads(raw)
        return raw
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    metin = raw.lstrip() if isinstance(raw, str) else ""
    if metin.startswith("{"):
        try:
            nesne, _son = json.JSONDecoder().raw_decode(metin)
        except (json.JSONDecodeError, ValueError):
            nesne = None
        if isinstance(nesne, dict):
            return json.dumps(nesne, ensure_ascii=False)
    return "{}"


def _to_wire(message: Message) -> dict[str, Any]:
    """Proje mesajını sağlayıcının beklediği sözlüğe çevir.

    Görsel yoksa içerik DÜZ METİN kalır: çok parçalı biçim bazı uçlarda desteklenmez
    ve gereksiz yere davranış değiştirir.
    """
    icerik: Any = message.content
    if message.images:
        icerik = [{"type": "text", "text": message.content}]
        icerik += [{"type": "image_url", "image_url": {"url": url}} for url in message.images]
    wire: dict[str, Any] = {"role": message.role, "content": icerik}
    if message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": _valid_arguments(call.arguments)},
            }
            for call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        wire["tool_call_id"] = message.tool_call_id
    if message.name is not None:
        wire["name"] = message.name
    return wire


def _chunk_text(chunk: Any) -> str:
    try:
        content = chunk.choices[0].delta.content
    except (AttributeError, IndexError, TypeError):
        return ""
    return str(content or "")


def _chunk_reasoning(chunk: Any) -> str:
    """Akış parçasındaki düşünme metni. Kullanıcıya METİN olarak yayınlanmaz."""
    try:
        delta = chunk.choices[0].delta
    except (AttributeError, IndexError, TypeError):
        return ""
    return _first_field(delta, _REASONING_FIELDS)


def build_messages(task: str, system: str | None = None) -> tuple[Message, ...]:
    """Basit bir görev metnini mesaj dizisine çevir."""
    if system:
        return (Message("system", system), Message("user", task))
    return (Message("user", task),)

"""LiteLLM adaptörü — tek bir modele çağrı yapar.

Sorumluluğu dardır ve bilinçlidir: SDK'yı çağırır, yanıtı `ModelResult`/`StreamItem`
tiplerine normalize eder. Yedekleme, yarıştırma ve olay yayını burada DEĞİL, üstteki
dekoratörlerdedir (`hedged.py`, `eventing.py`). Böylece yeni bir sağlayıcı eklemek
yalnızca bu dosyanın bir eşdeğerini yazmak olur; dayanıklılık davranışı bedava gelir.

LiteLLM 100+ sağlayıcıyı model kimliğinin "<sağlayıcı>/<model>" önekinden tanır;
ayrı bir proxy sunucusu çalıştırmaya gerek yoktur.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from ..core.clock import SystemClock
from ..core.protocols import Clock
from ..core.redaction import redact
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

    def __init__(self, model: str, *, role: str, clock: Clock | None = None) -> None:
        self._model = model
        self._role = role
        self._clock = clock or SystemClock()

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
            return self._failure(exc, started)
        return self._success(response, started)

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
        except Exception as exc:
            yield StreamDone(self._failure(exc, started))
            return
        yield StreamDone(self._rebuild(chunks, request, started))

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
        if stream:
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
        return kwargs

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
            )
        sonuc = self._success(rebuilt, started)
        if sonuc.reasoning or not akis_reasoning:
            return sonuc
        # `stream_chunk_builder` düşünme metnini her sağlayıcıda taşımaz; parçalardan
        # topladığımız metin varsa kaybedilmez.
        return replace(sonuc, reasoning=akis_reasoning)


# --------------------------------------------------------------------------- #
# SDK nesnelerini okuma — bu sınır dışına LiteLLM tipi sızmaz.
# --------------------------------------------------------------------------- #


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
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=estimate_cost(model, prompt_tokens, completion_tokens),
    )


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Modelin fiyat tablosuna göre tahmini maliyet (USD).

    Fiyat bilinmiyorsa (yeni ya da yerel model) 0 döner: bilinmeyen bir maliyeti
    uydurmaktansa sıfır göstermek dürüsttür.
    """
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
        _logger.debug("maliyet hesaplanamadı (model=%s): %s", model, exc)
        return 0.0
    return float(cost or 0.0)


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
            calls.append(
                ToolCall(
                    id=str(item.id),
                    name=str(item.function.name),
                    arguments=str(item.function.arguments or "{}"),
                )
            )
        except AttributeError:
            continue
    return tuple(calls)


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
                "function": {"name": call.name, "arguments": call.arguments},
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

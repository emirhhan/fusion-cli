"""Web-session sağlayıcı çerçevesi — oturum tabanlı uçları `LlmProvider`'a bağlar.

Bazı model kaynakları resmî API yerine bir OTURUM (bearer token, cookie) üzerinden
erişilir. Bu adaptör böyle bir kaynağı Fusion'ın canonical `LlmProvider` sözleşmesine
uydurur: `complete`/`stream` döndürür, hata fırlatmaz (`ok=False` sonuç taşır) ve
mevcut yığına (FallbackProvider, circuit breaker) sorunsuz oturur.

GÜVENLİK VE KAPSAM SINIRI: Bu çerçeve yalnızca kullanıcının kendi hesabı veya
yetkili ucu içindir. Native browser transport'u izole Fusion profilinde açık kullanıcı
girişiyle çalışır; normal tarayıcı profilini okumaz, CAPTCHA çözmez, fingerprint/anti-bot
korumasını aşmaz. Genel HTTP transport'u da kullanıcının kendi OpenAI-uyumlu ucuna bağlanır.

Araç desteği:
- `NONE`: araç yoktur; yalnızca düz sohbet/council. `request.tools` yok sayılır.
- `EMULATED`: araç tanımları `core.tool_emulation` ile prompt'a eklenir, yanıt
  `ToolCall`'a ayrıştırılır (eval eşiğini geçmeden mutation'a giremez, bkz. `tool_policy`).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace

from ..core.clock import SystemClock
from ..core.model_capability import ToolSupport
from ..core.protocols import Clock
from ..core.redaction import redact, strip_driver_log
from ..core.tool_emulation import escape_tool_markers, parse_tool_calls, render_tool_instructions
from ..core.types import (
    WEB_SESSION_ERROR_PREFIX,
    CompletionRequest,
    Message,
    ModelResult,
    StreamDone,
    StreamItem,
    TextChunk,
)

_logger = logging.getLogger(__name__)


def _brief_session_error(error: BaseException) -> str:
    """Kullanıcıya gidecek kısa hata metni; ham sürücü günlüğü yalnız günlük dosyasına."""
    detail = str(error)
    _logger.warning("web oturumu hatasi: %s: %s", type(error).__name__, redact(detail))
    brief = strip_driver_log(detail)
    # Sürücü adı ("Locator.click: Timeout 5000ms exceeded") kullanıcıya bir şey söylemez.
    if "Timeout" in brief and ("click" in brief.lower() or "locator" in brief.lower()):
        return "tarayıcı arayüzündeki bir öğe zamanında tıklanamadı"
    return brief or type(error).__name__


@dataclass(frozen=True, slots=True)
class WebSessionCredential:
    """Oturum tabanlı bir uca erişim bilgisi. Depoda düz tutulmaz; şifreli gelir."""

    token: str = ""
    cookies: Mapping[str, str] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WebTurn:
    """Bir web turunun sonucu: metin ve GÖZLENEN kademe.

    Düz `str` yetmiyordu. Tarayıcı taşımasında hangi modelin cevapladığına
    hesabın kendi arayüz seçimi karar veriyor; taşıma bunu görüyor ama üst
    katmanlara söyleyecek bir kanal yoktu. Sonuç: oturum düşüp Gemini anonim
    "Flash-Lite" kademesine indiğinde bile her yer `gemini_web/auto` diyordu.

    `tier` boşsa kademe BİLİNMİYOR demektir; "istenen kademe geldi" demek değildir.
    """

    text: str
    tier: str = ""
    #: Kullanıcıya TEK satır olarak gösterilecek not (ör. seçili mod pasif, mevcut kiple
    #: sürüldü). Cevabın parçası değildir; boşsa gösterilecek bir şey yok.
    note: str = ""


@dataclass(frozen=True, slots=True)
class WebTurnContext:
    """Üst katmanın taşımaya bildirdiği tur bağlamı (isteğe bağlı).

    - `conversation_id`: durumlu taşımanın sohbet anahtarına katılan iş kimliği (P1-31).
    - `answer_contract`: her araç turunda tekrarlanacak sözleşme metni; motor üretir,
      taşıma yalnız biçimlendirir (P1-33).

    Alanların hepsi boşsa taşıma bu bağlamı hiç görmez: adaptör eski 3 argümanlı
    çağrı biçimini kullanır (bağlamdan habersiz taşıma/test sahteleri kırılmasın).
    """

    conversation_id: str = ""
    answer_contract: str = ""

    @property
    def is_empty(self) -> bool:
        return not (self.conversation_id or self.answer_contract)


#: Gerçek I/O'yu yapan enjekte edilebilir transport: kimlik + mesajlar + model → tur.
#: Sahte (mock) ya da kullanıcının yetkili uca yazdığı gerçek transport olabilir.
#: Bağlam-bilen taşıma ek olarak `context: WebTurnContext` anahtar sözcüğünü kabul eder;
#: adaptör onu YALNIZ boş değilse geçirir. `...` bu yüzden: iki biçim de geçerlidir.
WebTransport = Callable[..., Awaitable[WebTurn]]


def _accepts_context(transport: WebTransport) -> bool:
    """Taşıma `context` anahtar sözcüğünü (ya da `**kwargs`) kabul ediyor mu?

    Bağlamdan habersiz 3 argümanlı taşımalar (eski/özel taşıma, test sahtesi) bağlam
    verilmeden çağrılır: yeni bir isteğe bağlı alan onları kırmamalı.
    """
    try:
        parameters = inspect.signature(transport).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        item.kind is inspect.Parameter.VAR_KEYWORD
        or (item.name == "context" and item.kind is not inspect.Parameter.POSITIONAL_ONLY)
        for item in parameters
    )


class WebProviderAdapter:
    """Oturum tabanlı bir kaynağı `LlmProvider` gibi gösteren adaptör."""

    def __init__(
        self,
        *,
        model: str,
        credential: WebSessionCredential,
        transport: WebTransport,
        tool_support: ToolSupport = ToolSupport.NONE,
        supports_images: bool = False,
        clock: Clock | None = None,
    ) -> None:
        self._model = model
        self._credential = credential
        self._transport = transport
        self._transport_takes_context = _accepts_context(transport)
        self._tool_support = tool_support
        self._supports_images = supports_images
        self._clock = clock or SystemClock()
        self._note_sink: Callable[[str], None] | None = None

    @property
    def label(self) -> str:
        return self._model

    def bind_note_sink(self, sink: Callable[[str], None]) -> None:
        """Taşımanın tek satırlık kullanıcı notlarını (`WebTurn.note`) ileteceği yer.

        Kurucuya değil ayrı bir çağrıya konuldu: `WebSessionRegistry.build` imzası ve onu
        taklit eden testler değişmesin. Sink hata fırlatırsa tur etkilenmez.
        """
        self._note_sink = sink

    async def complete(self, request: CompletionRequest) -> ModelResult:
        messages = self._prepared_messages(request)
        start = self._clock.monotonic()
        try:
            raw = await asyncio.wait_for(
                self._call_transport(request, messages),
                timeout=request.timeout_s,
            )
        except TimeoutError:
            latency = int((self._clock.monotonic() - start) * 1000)
            return ModelResult(
                name=self._model,
                model=self._model,
                text="",
                latency_ms=latency,
                ok=False,
                error="web oturumu zaman aşımı",
            )
        except Exception as error:
            # hata fırlatılmaz, `ok=False` sonuç taşınır. Web transport'ları çok çeşitli
            # biçimde başarısız olur (ağ, oturum süresi, biçim); hepsi sonuca çevrilir.
            latency = int((self._clock.monotonic() - start) * 1000)
            return ModelResult(
                name=self._model,
                model=self._model,
                text="",
                latency_ms=latency,
                ok=False,
                error=f"{WEB_SESSION_ERROR_PREFIX} {_brief_session_error(error)}",
            )
        latency = int((self._clock.monotonic() - start) * 1000)
        self._forward_note(getattr(raw, "note", ""))
        return self._to_result(raw.text, latency, served_by=raw.tier)

    def _forward_note(self, note: str) -> None:
        if not note or self._note_sink is None:
            return
        try:
            self._note_sink(note)
        except Exception:
            _logger.debug("web notu iletilemedi", exc_info=True)

    def _call_transport(
        self, request: CompletionRequest, messages: tuple[Message, ...]
    ) -> Awaitable[WebTurn]:
        """Taşımayı çağır; tur bağlamı yalnız doluysa geçirilir."""
        context = WebTurnContext(
            conversation_id=request.conversation_id,
            answer_contract=request.answer_contract if request.tools else "",
        )
        if context.is_empty or not self._transport_takes_context:
            return self._transport(self._credential, messages, self._model)
        return self._transport(self._credential, messages, self._model, context=context)

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        # Oturum tabanlı uçlar çoğu zaman akıtılamaz: tek seferde alınır, sonra parça
        # olarak yayınlanır. Protokol yine tek `StreamDone` ile biter.
        result = await self.complete(request)
        if result.text:
            chunk = self._chunk_for(result)
            if chunk is not None:
                yield chunk
        yield StreamDone(result)

    def _chunk_for(self, result: ModelResult) -> TextChunk | None:
        """Bu turun metni akıtılmalı mı, akıtılacaksa hangi nitelikte?

        Taklit araç sözleşmesinde bir yanıt iki şeyden biridir:

        - **Araç çağrısı VAR** → metin bir ÖNCÜDÜR ("şu dosyaya bakıyorum").
          Akıtılır ama `provisional` işaretiyle: nihai cevap değildir ve sunum
          katmanı onu cevap gibi göstermez.
        - **Araç çağrısı YOK** → metin bir ADAY nihai cevaptır. AKITILMAZ. Motorun
          kapıları (kanıt, otomatik devam) onu reddedip modeli tekrar çağırabilir;
          akıtmak, elenmiş bir cevabı kullanıcıya göstermek ya da model kendini
          tekrarladığında aynı metni iki kez basmak demekti. Kabul edilen cevabı
          motor `TurnAnswered` ile tek noktadan yayınlar.

        Ayrıştırma hatasında hiçbir şey akıtılmaz: `text` yarım kalmış bir çağrı
        ya da payload kalıntısı taşıyabilir.

        Taklit sözleşmesi kullanılmayan yol (düz sohbet, council) bu ayrımın
        DIŞINDADIR: orada araç çağrısı hiç üretilmez ve metni bastırmak ekranı
        tamamen boş bırakırdı.
        """
        if self._tool_support is not ToolSupport.EMULATED:
            return TextChunk(result.text)
        if result.error:
            return None
        return TextChunk(result.text, provisional=True) if result.tool_calls else None

    def _prepared_messages(self, request: CompletionRequest) -> tuple[Message, ...]:
        """Emulated araç desteğinde araç talimatlarını sistem mesajına ekle."""
        messages = tuple(self._prepare_images(message) for message in request.messages)
        if self._tool_support is ToolSupport.EMULATED:
            # Araç SONUCU dış içeriktir (sayfa, dosya, komut çıktısı): içindeki çağrı
            # işaretleri modelin yanıtına yansıyıp çağrı sayılmasın (C1-45).
            messages = tuple(self._escape_tool_result(message) for message in messages)
        if self._tool_support is not ToolSupport.EMULATED or not request.tools:
            return messages
        # Web yolunda çağrı METİNDEN üretilir: şema ne kadar şişkinse model o kadar
        # sık yanlış anahtar yazıyor. Sade biçim zorunlu alanları öne çıkarır;
        # opsiyonel alanlar araç açıklamasında zaten anlatılıyor.
        instructions = render_tool_instructions(request.tools, compact=True)
        return (Message("system", instructions), *messages)

    @staticmethod
    def _escape_tool_result(message: Message) -> Message:
        """Araç sonucu mesajındaki protokol işaretlerini ZWSP ile kaçışla."""
        if message.role != "tool":
            return message
        return replace(message, content=escape_tool_markers(message.content))

    def _prepare_images(self, message: Message) -> Message:
        """Native görsel taşımayan web yolunda kaybı açık bir gözleme dönüştür."""
        if self._supports_images or not message.images:
            return message
        notice = (
            f"[Bu mesajdaki {len(message.images)} görsel içeriği bu web taşımasında "
            "desteklenmiyor; görsel incelenmedi.]"
        )
        content = "\n\n".join(part for part in (message.content, notice) if part)
        return Message(
            role=message.role,
            content=content,
            tool_calls=message.tool_calls,
            tool_call_id=message.tool_call_id,
            name=message.name,
            ok=message.ok,
            harness_note=message.harness_note,
        )

    def _to_result(self, raw: str, latency_ms: int, *, served_by: str = "") -> ModelResult:
        """Ham yanıtı `ModelResult`'a çevir; emulated ise araç çağrılarını ayrıştır."""
        if self._tool_support is ToolSupport.EMULATED:
            parse = parse_tool_calls(raw)
            # KURTARILABİLİR olan kurtarılır. Ölçüldü: model doğru bir edit_file
            # üretip yanında kullanılmayan bir payload bıraktığında, çalışacak
            # düzenleme uygulanmadan atılıyordu — bir model çağrısı (~40 sn) ve bir
            # onarım hakkı yanıyor, model bağlamda "okuma başarılı / yazma hatalı"
            # görüyor ve rasyonel olarak okumaya kaçıyordu. Ayrıştırılabilen çağrı
            # varsa artıklar turu öldürmez; sözleşme hatası YALNIZCA hiçbir çağrı
            # kurtarılamadığında bildirilir.
            if parse.errors and not parse.calls:
                return ModelResult(
                    name=self._model,
                    model=self._model,
                    text=parse.text,
                    latency_ms=latency_ms,
                    ok=True,
                    error="TOOL_CALL_PARSE_ERROR: " + "; ".join(parse.errors),
                    tool_calls=(),
                    served_by=served_by,
                )
            return ModelResult(
                name=self._model,
                model=self._model,
                text=parse.text,
                latency_ms=latency_ms,
                ok=True,
                tool_calls=parse.calls,
                served_by=served_by,
            )
        return ModelResult(
            name=self._model,
            model=self._model,
            text=raw,
            latency_ms=latency_ms,
            ok=True,
            served_by=served_by,
        )

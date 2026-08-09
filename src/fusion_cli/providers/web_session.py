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

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field

from ..core.clock import SystemClock
from ..core.model_capability import ToolSupport
from ..core.protocols import Clock
from ..core.tool_emulation import parse_tool_calls, render_tool_instructions
from ..core.types import (
    CompletionRequest,
    Message,
    ModelResult,
    StreamDone,
    StreamItem,
    TextChunk,
)


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


#: Gerçek I/O'yu yapan enjekte edilebilir transport: kimlik + mesajlar + model → tur.
#: Sahte (mock) ya da kullanıcının yetkili uca yazdığı gerçek transport olabilir.
WebTransport = Callable[[WebSessionCredential, tuple[Message, ...], str], Awaitable[WebTurn]]


class WebProviderAdapter:
    """Oturum tabanlı bir kaynağı `LlmProvider` gibi gösteren adaptör."""

    def __init__(
        self,
        *,
        model: str,
        credential: WebSessionCredential,
        transport: WebTransport,
        tool_support: ToolSupport = ToolSupport.NONE,
        clock: Clock | None = None,
    ) -> None:
        self._model = model
        self._credential = credential
        self._transport = transport
        self._tool_support = tool_support
        self._clock = clock or SystemClock()

    @property
    def label(self) -> str:
        return self._model

    async def complete(self, request: CompletionRequest) -> ModelResult:
        messages = self._prepared_messages(request)
        start = self._clock.monotonic()
        try:
            raw = await self._transport(self._credential, messages, self._model)
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
                error=f"web oturumu hatası: {error}",
            )
        latency = int((self._clock.monotonic() - start) * 1000)
        return self._to_result(raw.text, latency, served_by=raw.tier)

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
        if self._tool_support is not ToolSupport.EMULATED or not request.tools:
            return request.messages
        instructions = render_tool_instructions(request.tools)
        return (Message("system", instructions), *request.messages)

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

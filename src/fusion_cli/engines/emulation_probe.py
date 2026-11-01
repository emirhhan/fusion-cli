"""Taklit araç yeteneğini GERÇEK çağrılarla ölç.

`tools.emulation_eval` saf puanlayıcıdır: modelin çıktısını alır, puan verir. Bu modül
o çıktıyı üretir — yapılandırılmış bir web oturumuna küçük ve sabit bir senaryo kümesi
sorar, ham yanıtları toplar ve puanlatır.

Neden gerekli: `config.tool_policy` doğrulanmamış taklit-araç modelinin dosya
değiştirmesine izin vermez. İzni açacak tek şey ÖLÇÜMDÜR; "herhalde yapar" değil.

Neden `engines` altında: hem `providers` (çağrıyı yapan) hem `tools` (puanlayan)
katmanlarını birlikte kullanır. RULES.md'deki bağımlılık yönü yalnızca burada geçerlidir.

Ham çıktı nasıl alınır: adaptör `EMULATED` kipinde yanıtı ayrıştırır ve metni tüketir.
Sonda oturumu geçici olarak `none` araç desteğiyle kurar — böylece yanıt olduğu gibi
döner — ve araç talimatlarını sistem mesajı olarak KENDİSİ ekler. Ölçülen şey budur:
model, talimatı gördüğünde doğru bloğu üretebiliyor mu?
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from ..config.models import Config, WebSessionConfig
from ..core.errors import FusionError
from ..core.tool_emulation import (
    CALL_OPEN,
    LEGACY_CALL_OPEN,
    parse_tool_calls,
    render_tool_instructions,
)
from ..core.types import CompletionRequest, Message, TokenUsage
from ..core.web_provenance import WebCallContext, WebResponseProvenance
from ..providers.web_registry import WebSessionRegistry, web_registry_for
from ..tools import build_registry
from ..tools.emulation_eval import EmulationEvalScore, EvalCase, ExpectedCall, score_emulation

#: Sonda çağrısı için üst süre sınırı (saniye). Web arayüzleri yavaştır; ölçüm
#: kullanıcıyı süresiz bekletmemelidir.
PROBE_TIMEOUT_S = 120.0

#: Sonda çağrısının çıktı bütçesi. Senaryolar tek araç çağrısı ister; uzun cevaba
#: gerek yoktur ve kısa tutmak kullanıcının aboneliğini korur.
PROBE_MAX_TOKENS = 512


@dataclass(frozen=True, slots=True)
class ProbeSample:
    """Tek senaryonun HAM kaydı — ölçüm neden düştü sorusunun tek cevabı.

    Yalnızca puan raporlamak teşhis için yetmiyor: "araç seçimi %0" hem "model
    reddetti" hem "blok arayüzde yutuldu" anlamına gelebilir ve ikisinin çözümü
    tamamen farklıdır. Ham çıktı olmadan aralarında seçim yapmak tahmindir.
    """

    prompt: str
    expected_tool: str | None
    raw_output: str
    parsed_tool: str | None
    parse_errors: tuple[str, ...]
    web_provenance: WebResponseProvenance | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)

    @property
    def has_call_markers(self) -> bool:
        """Çıktıda sınır işareti GÖRÜNÜYOR mu?

        Görünmüyorsa iki ihtimal ayrışır: model bloğu hiç üretmedi ya da tarayıcı
        arayüzü `<tool_call>` etiketini HTML sanıp yuttu. İkincisinde metinde
        kaçırılmış (`&lt;`) biçim ya da hiçbir iz kalmaz.
        """
        return any(
            marker in self.raw_output for marker in (CALL_OPEN, LEGACY_CALL_OPEN, "tool_call")
        )


@dataclass(frozen=True, slots=True)
class ProbeLimits:
    """Açık kayıt çağrısı için saklama bütçesi; ilk DOM allocation sınırı değildir."""

    max_calls: int
    max_response_bytes: int
    max_total_bytes: int
    timeout_s: float

    def validate(self, count: int) -> None:
        values = (self.max_calls, self.max_response_bytes, self.max_total_bytes, self.timeout_s)
        if not all(math.isfinite(value) and value > 0 for value in values):
            raise FusionError("Sonda bütçeleri pozitif olmalı.")
        if count > self.max_calls:
            raise FusionError("Senaryo sayısı çağrı bütçesini aşıyor.")


@dataclass(frozen=True, slots=True)
class ProbeReport:
    """Ölçüm sonucu + her senaryonun ham kaydı."""

    score: EmulationEvalScore
    samples: tuple[ProbeSample, ...]
    cases: tuple[EvalCase, ...] = ()


@dataclass(frozen=True, slots=True)
class ProbeScenario:
    """Tek bir ölçüm senaryosu: modele sorulan istek + beklenen davranış."""

    prompt: str
    expected_tool: str | None
    #: Birebir eşleşmesi beklenen argümanlar. `None` ise yalnızca şema doğrulanır —
    #: model kod ürettiğinde birebir eşleşme beklemek anlamsızdır.
    expected_arguments: Mapping[str, object] | None = None
    expected_calls: tuple[ExpectedCall, ...] | None = None


#: Sabit senaryo kümesi. Az ve kasıtlı: her senaryo kullanıcının KENDİ aboneliğinden
#: bir çağrı harcar. Dördü araç üretmeli, biri hiç araç üretmemeli.
PROBE_SCENARIOS: tuple[ProbeScenario, ...] = (
    ProbeScenario(
        prompt="src/app.py dosyasının içeriğini oku. Başka hiçbir şey yapma.",
        expected_tool="read_file",
        expected_arguments={"path": "src/app.py"},
    ),
    ProbeScenario(
        prompt="Şu komutu çalıştır: python3 -m pytest -q — başka hiçbir şey yapma.",
        expected_tool="run_shell",
        expected_arguments={"command": "python3 -m pytest -q"},
    ),
    ProbeScenario(
        prompt=(
            "greet.py adında bir dosya oluştur. İçinde name parametresi alan ve "
            "'Hello, <name>!' döndüren greet fonksiyonu olsun. Çok satırlı içerik için "
            "payload biçimini kullan."
        ),
        # Kod üretimi: birebir argüman beklenmez, ŞEMA ve payload taşıması ölçülür.
        expected_tool="write_file",
    ),
    ProbeScenario(
        prompt="Projede 'TODO' geçen yerleri ara. Başka hiçbir şey yapma.",
        expected_tool="search_code",
        expected_arguments={"pattern": "TODO"},
    ),
    ProbeScenario(
        # Sahte çağrı ölçümü: burada araç çağırmak HATADIR.
        prompt="Python'da liste ile demet arasındaki fark nedir? Tek cümleyle açıkla.",
        expected_tool=None,
    ),
)


#: Sağlayıcıların oran sınırı hatalarında geçen işaretler.
_ORAN_ISARETLERI = ("rate-limit", "rate_limit", "rate limit", "too many requests", "oran sınırı")


def _oran_siniri_mi(hata: str) -> bool:
    """Hata metni oran sınırını mı söylüyor?

    İşaretler sağlayıcının KENDİ metninden okunur; Fusion kendi kalıbını uydurmaz.
    """
    kucuk = hata.casefold()
    return any(isaret in kucuk for isaret in _ORAN_ISARETLERI)


def _schema_of(tool_name: str) -> Mapping[str, object] | None:
    for schema in build_registry().schemas():
        function = schema.get("function")
        if isinstance(function, Mapping) and function.get("name") == tool_name:
            return function
    return None


def _probe_session(session: WebSessionConfig) -> WebSessionConfig:
    """Ham yanıt almak için araç desteği kapatılmış bir oturum kopyası."""
    return replace(session, tool_support="none")


async def probe_emulation(
    config: Config,
    model: str,
    *,
    registry: WebSessionRegistry | None = None,
    scenarios: Sequence[ProbeScenario] = PROBE_SCENARIOS,
    limits: ProbeLimits | None = None,
    call_contexts: Sequence[WebCallContext] = (),
    protocol: str = "v1",
) -> ProbeReport:
    """Bir web oturumunun taklit araç yeteneğini ölç.

    Senaryolar SIRAYLA çalışır: tarayıcı tabanlı oturumlar tek sayfayı paylaşır ve
    paralel istek göndermek oturumu bozar.
    """
    if protocol not in {"v1", "v2"}:
        raise FusionError("Taklit protokolü v1 veya v2 olmalı.")
    if limits is not None:
        limits.validate(len(scenarios))
    if call_contexts and len(call_contexts) != len(scenarios):
        raise FusionError("Her senaryo için tek uygulama çağrı bağlamı gerekli.")
    timeout_s = limits.timeout_s if limits else PROBE_TIMEOUT_S
    total_bytes = 0
    sessions = registry or web_registry_for(config)
    session = next(
        (item for item in config.web_sessions if item.model == model and item.enabled), None
    )
    if sessions is None or session is None:
        raise FusionError(f"'{model}' için etkin bir web oturumu yok.")

    # Oturumun KOPYASI verilir, model kimliği değil: kimlik aynı kaldığı için
    # `build(model)` orijinal (emulated) oturumu bulur ve araç bloklarını metinden
    # çıkarırdı — sonda ham çıktı yerine boş metin görürdü.
    provider = sessions.build_session(_probe_session(session))

    instructions = render_tool_instructions(build_registry().schemas())
    cases: list[EvalCase] = []
    samples: list[ProbeSample] = []
    # Geçmiş BİRİKEREK gider ve ilk mesaj hep aynı kalır: web taşıması sohbeti
    # yalnızca gönderilen önek değişmediyse sürdürür (bkz.
    # `web_browser.ConversationState`). Her senaryoyu iki mesajlık taze bir
    # istekle göndermek her senaryoda YENİ sohbet açıyordu.
    #
    # Ölçüldü (13 Eylül, kullanıcı makinesi): senaryo başına yeni sohbet, ekranda
    # on dörde yakın sekme açtı ve sağlayıcı bunu bot davranışı sayıp konuşma
    # oranı sınırını uyguladı — ölçüm de, kullanıcının o gün kalan kotası da gitti.
    history: list[Message] = [Message("system", instructions)]
    for index, scenario in enumerate(scenarios):
        history.append(Message("user", scenario.prompt))
        request = CompletionRequest(
            messages=tuple(history),
            temperature=0.0,
            max_tokens=PROBE_MAX_TOKENS,
            timeout_s=timeout_s,
            emulation_protocol="v2" if protocol == "v2" else "v1",
            web_call_context=call_contexts[index] if call_contexts else None,
            is_capture_probe=limits is not None,
            conversation_id=call_contexts[index].session_id if call_contexts else "",
        )
        try:
            result = await asyncio.wait_for(provider.complete(request), timeout=timeout_s)
        except TimeoutError as error:
            raise FusionError(
                f"Ölçüm zaman aşımına uğradı ({scenario.expected_tool or 'araçsız'} senaryosu)."
            ) from error
        if not result.ok:
            if _oran_siniri_mi(result.error or ""):
                # Sınıra takılmışken denemeye devam etmek sınırı DERİNLEŞTİRİR:
                # her deneme yeni bir konuşma isteğidir. Ölçüm burada durur.
                raise FusionError(
                    "Sağlayıcı oran sınırına takıldı; ölçüm durduruldu. Sınır kalkınca tekrar dene."
                )
            raise FusionError(f"Ölçüm sırasında sağlayıcı hatası: {result.error}")
        if limits is not None and result.truncated:
            raise FusionError("Kesilmiş yanıt tamamlanmış kayıt olarak kabul edilmedi.")
        response_bytes = len(result.text.encode("utf-8"))
        total_bytes += response_bytes
        if limits and (
            response_bytes > limits.max_response_bytes or total_bytes > limits.max_total_bytes
        ):
            raise FusionError("Yanıt saklama bütçesini aşıyor; kırpılmış örnek kabul edilmedi.")
        history.append(Message("assistant", result.text))
        cases.append(
            EvalCase(
                output=result.text,
                expected_tool=scenario.expected_tool,
                expected_arguments=scenario.expected_arguments,
                expected_calls=scenario.expected_calls,
                schema=_schema_of(scenario.expected_tool) if scenario.expected_tool else None,
                case_id=f"probe-{index}",
                provider=model,
                transport=session.transport,
                provenance="synthetic",
                split="diagnostic",
                usage=result.usage,
                protocol=protocol,
                web_provenance=result.web_provenance,
            )
        )
        parsed = parse_tool_calls(
            result.text,
            protocol=protocol,
            provenance=result.web_provenance,
            call_context=request.web_call_context,
        )
        samples.append(
            ProbeSample(
                prompt=scenario.prompt,
                expected_tool=scenario.expected_tool,
                raw_output=result.text,
                parsed_tool=parsed.calls[0].name if parsed.calls else None,
                parse_errors=parsed.errors,
                web_provenance=result.web_provenance,
                usage=result.usage,
            )
        )
    return ProbeReport(score=score_emulation(cases), samples=tuple(samples), cases=tuple(cases))

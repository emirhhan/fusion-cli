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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from ..config.models import Config, WebSessionConfig
from ..core.errors import FusionError
from ..core.tool_emulation import CALL_OPEN, parse_tool_calls, render_tool_instructions
from ..core.types import CompletionRequest, Message
from ..providers.web_registry import WebSessionRegistry, web_registry_for
from ..tools import build_registry
from ..tools.emulation_eval import EmulationEvalScore, EvalCase, score_emulation

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

    @property
    def has_call_markers(self) -> bool:
        """Çıktıda sınır işareti GÖRÜNÜYOR mu?

        Görünmüyorsa iki ihtimal ayrışır: model bloğu hiç üretmedi ya da tarayıcı
        arayüzü `<tool_call>` etiketini HTML sanıp yuttu. İkincisinde metinde
        kaçırılmış (`&lt;`) biçim ya da hiçbir iz kalmaz.
        """
        return CALL_OPEN in self.raw_output or "tool_call" in self.raw_output.lower()


@dataclass(frozen=True, slots=True)
class ProbeReport:
    """Ölçüm sonucu + her senaryonun ham kaydı."""

    score: EmulationEvalScore
    samples: tuple[ProbeSample, ...]


@dataclass(frozen=True, slots=True)
class ProbeScenario:
    """Tek bir ölçüm senaryosu: modele sorulan istek + beklenen davranış."""

    prompt: str
    expected_tool: str | None
    #: Birebir eşleşmesi beklenen argümanlar. `None` ise yalnızca şema doğrulanır —
    #: model kod ürettiğinde birebir eşleşme beklemek anlamsızdır.
    expected_arguments: Mapping[str, object] | None = None


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
) -> ProbeReport:
    """Bir web oturumunun taklit araç yeteneğini ölç.

    Senaryolar SIRAYLA çalışır: tarayıcı tabanlı oturumlar tek sayfayı paylaşır ve
    paralel istek göndermek oturumu bozar.
    """
    sessions = registry or web_registry_for(config)
    session = next(
        (item for item in config.web_sessions if item.model == model and item.enabled), None
    )
    if sessions is None or session is None:
        raise FusionError(f"'{model}' için etkin bir web oturumu yok.")

    provider = sessions.build(_probe_session(session).model)
    if provider is None:
        raise FusionError(f"'{model}' için web sağlayıcısı kurulamadı.")

    instructions = render_tool_instructions(build_registry().schemas())
    cases: list[EvalCase] = []
    samples: list[ProbeSample] = []
    for scenario in scenarios:
        request = CompletionRequest(
            messages=(Message("system", instructions), Message("user", scenario.prompt)),
            temperature=0.0,
            max_tokens=PROBE_MAX_TOKENS,
            timeout_s=PROBE_TIMEOUT_S,
        )
        try:
            result = await asyncio.wait_for(
                provider.complete(request), timeout=PROBE_TIMEOUT_S + 10
            )
        except TimeoutError as error:
            raise FusionError(
                f"Ölçüm zaman aşımına uğradı ({scenario.expected_tool or 'araçsız'} senaryosu)."
            ) from error
        if not result.ok:
            raise FusionError(f"Ölçüm sırasında sağlayıcı hatası: {result.error}")
        cases.append(
            EvalCase(
                output=result.text,
                expected_tool=scenario.expected_tool,
                expected_arguments=scenario.expected_arguments,
                schema=_schema_of(scenario.expected_tool) if scenario.expected_tool else None,
            )
        )
        parsed = parse_tool_calls(result.text)
        samples.append(
            ProbeSample(
                prompt=scenario.prompt,
                expected_tool=scenario.expected_tool,
                raw_output=result.text,
                parsed_tool=parsed.calls[0].name if parsed.calls else None,
                parse_errors=parsed.errors,
            )
        )
    return ProbeReport(score=score_emulation(cases), samples=tuple(samples))

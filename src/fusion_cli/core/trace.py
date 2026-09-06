"""Koşu izi — olaylardan tek bakışta teşhis.

Ölçüldü (5 Eylül canlı koşusu): 24 görevlik setteki beş başarısızlığın sebebini
bulmak için transkript dosyaları elle okundu ve sebep ancak saatler sonra "araç
kapsamı adımı imkânsız kılmış" diye adlandırılabildi. Kayıp SINIFI olayların
kendisinden çıkarılabilir; bu modül o çıkarımı saf ve test edilebilir yapar.

Saf tutulur: dosya, konsol ve ağ bilmez. Girdi olay dizisi, çıktı özet nesnesidir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .events import (
    ErrorOccurred,
    Event,
    ExecutionPaused,
    ExecutionStepStarted,
    ExecutionStepVerified,
    ModelCallFinished,
    ToolCallRepaired,
    ToolExecuted,
    ToolOutcome,
)

#: Kapsam engelinin metni. Motor bu cümleyi tek yerde üretir (`loop._execute`);
#: taksonomi metne bakar çünkü olay tipi "engellendi" der ama SEBEBİNİ taşımaz.
_SCOPE_MARK = "izin verilen kapsamında değil"
#: Mutasyon kapısının engellediği çağrının metin işareti.
_MUTATION_MARK = "değişiklik yapamaz"


class FailureKind(StrEnum):
    """Bir koşuda gözlenen kayıp sınıfı.

    Sınıflar ÇAKIŞMAZ diye bir kural yoktur: bir koşu hem sağlayıcı hatası hem
    doğrulama hatası taşıyabilir. Amaç tek bir "asıl sebep" uydurmak değil, elde
    hangi kanıtın olduğunu söylemektir.
    """

    TOOL_SCOPE = "arac_kapsami"
    TOOL_FAILURE = "arac_hatasi"
    APPROVAL = "onay"
    PARSE = "ayristirma"
    EMPTY_RESPONSE = "bos_yanit"
    PROVIDER = "saglayici"
    VERIFICATION = "dogrulama"
    BUDGET = "butce"
    FATAL = "olumcul"


#: Kayıp sınıfının kullanıcıya gösterilecek karşılığı ve ilk bakılacak yer.
_HEADLINES: dict[FailureKind, str] = {
    FailureKind.TOOL_SCOPE: "araç kapsamı adımın işini engelledi",
    FailureKind.TOOL_FAILURE: "araç çağrıları başarısız oldu",
    FailureKind.APPROVAL: "onay alınamadı (etkileşimsiz oturum ya da ret)",
    FailureKind.PARSE: "araç çağrısı biçimi onarılmak zorunda kaldı",
    FailureKind.EMPTY_RESPONSE: "model boş yanıt döndürdü",
    FailureKind.PROVIDER: "sağlayıcı hata verdi",
    FailureKind.VERIFICATION: "doğrulama kapısı düştü",
    FailureKind.BUDGET: "bütçe tükendi",
    FailureKind.FATAL: "tur ölümcül hatayla bitti",
}


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Bir koşunun sayıları ve gözlenen kayıp sınıfları."""

    failures: tuple[FailureKind, ...] = ()
    model_calls: int = 0
    tool_calls: int = 0
    blocked_tools: int = 0
    failed_tools: int = 0
    parse_repairs: int = 0
    steps: int = 0
    verified_steps: int = 0
    pause_reason: str = ""
    findings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        """Hiçbir kayıp sınıfı gözlenmediyse koşu temizdir."""
        return not self.failures

    def headline(self) -> str:
        """Tek satırlık teşhis: önce en erken zincir halkası yazılır."""
        if not self.failures:
            return "temiz koşu"
        return "; ".join(_HEADLINES[kind] for kind in self.failures)


def summarize_run(events: list[Event] | tuple[Event, ...]) -> RunSummary:
    """Olay dizisini sayılara ve kayıp sınıflarına indir."""
    kinds: list[FailureKind] = []
    model_calls = tool_calls = blocked = failed = repairs = steps = verified = 0
    pause_reason = ""
    findings: list[str] = []

    for event in events:
        if isinstance(event, ModelCallFinished):
            model_calls += 1
            if event.result.error:
                _add(kinds, FailureKind.PROVIDER)
            elif not event.result.text.strip() and not event.result.tool_calls:
                _add(kinds, FailureKind.EMPTY_RESPONSE)
        elif isinstance(event, ToolExecuted):
            tool_calls += 1
            if event.outcome is ToolOutcome.BLOCKED:
                blocked += 1
                _add(kinds, _blocked_kind(event.output))
            elif event.outcome is ToolOutcome.DENIED:
                blocked += 1
                _add(kinds, FailureKind.APPROVAL)
            elif event.outcome is ToolOutcome.FAILED:
                failed += 1
                _add(kinds, FailureKind.TOOL_FAILURE)
        elif isinstance(event, ToolCallRepaired):
            repairs += 1
            _add(kinds, FailureKind.PARSE)
        elif isinstance(event, ExecutionStepStarted):
            steps += 1
        elif isinstance(event, ExecutionStepVerified):
            if event.ok:
                verified += 1
            else:
                _add(kinds, FailureKind.VERIFICATION)
                findings.extend(event.findings)
        elif isinstance(event, ExecutionPaused):
            pause_reason = event.reason
            if "bütçe" in event.reason.casefold():
                _add(kinds, FailureKind.BUDGET)
        elif isinstance(event, ErrorOccurred) and event.fatal:
            _add(kinds, FailureKind.FATAL)
            findings.append(event.message)

    return RunSummary(
        failures=tuple(kinds),
        model_calls=model_calls,
        tool_calls=tool_calls,
        blocked_tools=blocked,
        failed_tools=failed,
        parse_repairs=repairs,
        steps=steps,
        verified_steps=verified,
        pause_reason=pause_reason,
        findings=tuple(findings),
    )


def _blocked_kind(output: str) -> FailureKind:
    """Engellenen çağrının SEBEBİNİ metninden ayır.

    Kapsam engeli ile mutasyon/onay engeli aynı olay tipini paylaşır ama farklı
    işlerdir: ilki plan hatasıdır, ikincisi güvenlik kararıdır.
    """
    lowered = output.casefold()
    if _SCOPE_MARK in lowered:
        return FailureKind.TOOL_SCOPE
    if _MUTATION_MARK in lowered:
        return FailureKind.APPROVAL
    return FailureKind.APPROVAL


def _add(kinds: list[FailureKind], kind: FailureKind) -> None:
    """Sınıfı ilk görüldüğü sırayla, tekrarsız ekle."""
    if kind not in kinds:
        kinds.append(kind)

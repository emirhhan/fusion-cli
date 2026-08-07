"""Olay sözlüğü — motor katmanının dış dünyayla tek konuşma biçimi.

Eski projede motorlar doğrudan konsola yazıyordu; bu yüzden alt-ajan çıktısı ana
ajanınkine karışıyor, ham log satırları akışın ortasına düşüyordu. Burada motorlar
konsolu hiç tanımaz: tiplenmiş olay yayınlar, olayları tek bir veriyolu SIRAYLA
dinleyicilere dağıtır. Çakışma yapısal olarak imkânsız hale gelir.

`Channel` alanı ikinci güvenceyi verir: ana ajan, alt-ajan ve council farklı
kanallarda akar; dinleyici her kanalı ayrı tamponlar, satırlar birbirini bölmez.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .types import FusionResult, ModelResult


class Channel(Enum):
    """Metin akışının hangi konuşmaya ait olduğu."""

    MAIN = "main"
    SUBAGENT = "subagent"
    COUNCIL = "council"


@dataclass(frozen=True, slots=True)
class Event:
    """Tüm olayların kökü."""


@dataclass(frozen=True, slots=True)
class StatusChanged(Event):
    """Kullanıcıya gösterilecek kısa ilerleme bilgisi."""

    message: str


@dataclass(frozen=True, slots=True)
class ModelCallStarted(Event):
    """Bir model çağrısı başlatıldı."""

    role: str
    model: str
    #: Arka plan işi mi? (hakem, sentez, öz-denetim, ders çıkarımı…)
    #: Bu çağrılar kullanıcıya ilerleme satırı olarak GÖSTERİLMEZ ama muhasebeye
    #: girer. Görünürlük ile muhasebe ayrı şeylerdir; eski projede birbirine
    #: karıştıkları için maliyet takibi çağrı yollarını sessizce atlıyordu.
    background: bool = False


@dataclass(frozen=True, slots=True)
class ModelCallFinished(Event):
    """Bir model çağrısı bitti (başarılı ya da değil)."""

    role: str
    result: ModelResult
    #: Arka plan işi mi? Bkz. `ModelCallStarted.background`.
    background: bool = False


@dataclass(frozen=True, slots=True)
class ModelFallbackActivated(Event):
    """Birincil kullanılamadı ve sıradaki modele geçiliyor.

    Bu olay olmazsa dıştaki ``EventingProvider`` yalnızca zincirin baş modelini ve
    en son başarılı sonucu görür; aradaki hata sessiz kalır. Kullanıcı seçtiği
    modelin neden değiştiğini görebilmelidir.
    """

    role: str
    requested_model: str
    fallback_model: str
    reason: str
    background: bool = False


@dataclass(frozen=True, slots=True)
class TokenReceived(Event):
    """Akıştan metin parçası geldi."""

    channel: Channel
    text: str


@dataclass(frozen=True, slots=True)
class ErrorOccurred(Event):
    """Kullanıcıya gösterilecek hata. `fatal` ise tur devam edemez."""

    message: str
    fatal: bool = False


@dataclass(frozen=True, slots=True)
class CandidatesStarted(Event):
    """Aday modeller paralel olarak çalışmaya başladı."""

    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JudgingStarted(Event):
    """Hakem (ve istenmişse sentez) aşaması başladı."""

    with_synthesis: bool


@dataclass(frozen=True, slots=True)
class FusionCompleted(Event):
    """Fusion turu bitti; nihai cevap ve aday kayıtları hazır."""

    result: FusionResult


class ToolOutcome(Enum):
    """Bir araç çağrısının görünür sonucu.

    Reddedilme ne başarı ne hatadır; kullanıcıya da öyle gösterilmemelidir.
    """

    OK = "ok"
    FAILED = "failed"
    DENIED = "denied"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class ToolExecuted(Event):
    """Bir araç çağrısı sonuçlandı."""

    name: str
    args: Mapping[str, object]
    outcome: ToolOutcome
    output: str
    #: Değiştirici dosya araçları için, çalıştırılmadan ÖNCE üretilmiş unified diff
    #: (veya yeni dosya önizlemesi). Renderer bunu yeşil/kırmızı bir blok olarak basar.
    #: Diff dosya değişmeden önce üretilebildiği için burada taşınır; None ise araç
    #: değiştirici değildir ya da önizleme üretilememiştir.
    diff: str | None = None


@dataclass(frozen=True, slots=True)
class SubAgentStarted(Event):
    """Bir alt-göreve temiz bağlamlı alt-ajan atandı."""

    task: str


@dataclass(frozen=True, slots=True)
class SubAgentFinished(Event):
    """Alt-ajan işini bitirdi."""

    tool_calls: int


@dataclass(frozen=True, slots=True)
class CouncilConsulted(Event):
    """Zor bir karar için çoklu-model danışması başlatıldı."""

    question: str


@dataclass(frozen=True, slots=True)
class SelfReviewStarted(Event):
    """Tur sonrası öz-denetim başladı."""


@dataclass(frozen=True, slots=True)
class SelfReviewFinished(Event):
    """Öz-denetim bitti. `issue_found` ise düzeltici tur çalışacak."""

    issue_found: bool


@dataclass(frozen=True, slots=True)
class VerificationFailed(Event):
    """Doğrulama kapısı somut ihlal buldu; düzeltici tur çalışacak."""

    summary: str
    findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LessonsRecalled(Event):
    """Göreve benzer dersler hatırlandı ve prompta eklendi."""

    count: int


@dataclass(frozen=True, slots=True)
class LessonsLearned(Event):
    """Turdan yeni ders(ler) çıkarılıp belleğe yazıldı."""

    count: int


@dataclass(frozen=True, slots=True)
class ContextCompressed(Event):
    """Uzun geçmiş özetlenerek kısaltıldı."""

    before: int
    after: int


@dataclass(frozen=True, slots=True)
class MutationUnavailable(Event):
    """Seçili model dosya/sistem değiştiremiyor ve tur bunu gerektiriyor olabilir.

    Yetenek kapısı SESSİZ çalışmamalıdır. Değiştirici araçların şeması modele hiç
    sunulmuyorsa model "böyle bir aracım yok" der ve bu doğrudur — ama kullanıcı
    kısıtın nereden geldiğini ve nasıl kaldıracağını göremezse Fusion'ı arızalı
    sanır. Ölçüldü: kullanıcı Gemini'ye arka plandaki uygulamayı kapattırmak istedi,
    model aracı olmadığını söyledi, kısıtın sebebi hiçbir yerde görünmedi.

    `blocking` True ise görev bu yetenek olmadan tamamlanamaz ve tur hiç model
    çağrısı harcamadan bitirilmiştir.
    """

    reason: str
    blocking: bool = False


@dataclass(frozen=True, slots=True)
class TurnBudgetExhausted(Event):
    """Tur bütçesi doldu ve tur kesildi.

    Kullanıcı turun NEDEN bittiğini görmelidir. Sessizce durmak, kullanıcının aynı
    isteği tekrar denemesine ve aynı döngüye yeniden girmesine yol açıyordu.

    `reason` `core.budget.BudgetStop` değeridir; kullanıcı metnine `ui` katmanında
    çevrilir. Sayaçlar teşhis içindir: hangi bütçenin dolduğu tek bakışta görünür.
    """

    reason: str
    model_calls: int
    tool_rounds: int
    idle_rounds: int
    elapsed_s: float


@dataclass(frozen=True, slots=True)
class EffectWorkflowStarted(Event):
    """Deterministik bir gerçek-etki workflow'u başladı."""

    workflow_id: str
    kind: str
    title: str


@dataclass(frozen=True, slots=True)
class EffectWorkflowProgress(Event):
    """Workflow ilerleme aşaması; doğal dil iddiası değil, runtime durumudur."""

    workflow_id: str
    stage: str
    message: str


@dataclass(frozen=True, slots=True)
class EffectWorkflowFinished(Event):
    """Workflow deterministik post-condition sonucu ile kapandı."""

    workflow_id: str
    kind: str
    status: str
    ok: bool
    title: str
    details: Mapping[str, object]
    message: str


@dataclass(frozen=True, slots=True)
class TurnFinished(Event):
    """Tur bitti; dinleyiciler tamponlarını boşaltabilir."""


@runtime_checkable
class EventSink(Protocol):
    """Olayları tüketen taraf (terminal render'ı, JSON çıktısı, dosya log'u…).

    `handle` senkrondur ve hızlı dönmelidir; veriyolu olayları sırayla dağıtır.
    """

    def handle(self, event: Event) -> None: ...


class EventPublisher(Protocol):
    """Olay yayınlayan taraf. Motorlar yalnızca bunu görür, veriyolunu tanımaz.

    `publish` asla bloklamaz ve asla hata fırlatmaz.
    """

    def publish(self, event: Event) -> None: ...

"""Bir KULLANICI turunun tamamı için tek sayaç otoritesi.

Neden gerekli — ölçülmüş bir hata:

Agent döngüsünün sayaçları turu süren fonksiyonun YEREL durumundaydı. Öz-denetim
ve doğrulama kapısı düzeltmeyi `run_agent`'ı YENİDEN çağırarak yapar; her yeniden
çağrı o yerel durumu sıfırdan kuruyordu. Sonuç: bütçeler toplanmıyor, çarpılıyordu.

    ana tur        : 200 adım · 2 boş cevap · 1 sözleşme onarımı
    öz-denetim turu: 200 adım · 2 boş cevap · 1 sözleşme onarımı   (sıfırdan)
    düzeltme turu 1: 200 adım · 2 boş cevap · 1 sözleşme onarımı   (sıfırdan)
    düzeltme turu 2: 200 adım · 2 boş cevap · 1 sözleşme onarımı   (sıfırdan)

Kullanıcının gördüğü "bir türlü bitmeyen tur" buydu. `TurnBudget` tur başında BİR
KEZ kurulur ve iç içe her çağrıya aynı nesne geçirilir; sayaçlar tek yerde birikir.

Ayrıca "aynı çağrıyı tekrar etme" ve "ilerleme yok" tespiti de buradadır: ikisi de
yalnızca turun TAMAMI görülerek doğru cevaplanabilir. Düzeltici tur ana turdaki
çağrıyı birebir tekrar ediyorsa bu, ayrı ayrı bakıldığında görünmeyen bir döngüdür.

Modül saftır: yapılandırma okumaz, olay yayınlamaz, saati `Clock` üzerinden alır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .protocols import Clock


class BudgetStop(Enum):
    """Turun neden durdurulduğu.

    Kullanıcıya gösterilecek METİN burada değildir; kod `ui` katmanında metne
    çevrilir (RULES.md "UI ve CLI": motor kullanıcı metni üretmez).
    """

    MODEL_CALLS = "model_calls"
    TOOL_ROUNDS = "tool_rounds"
    DEADLINE = "deadline"
    NO_PROGRESS = "no_progress"
    REPEATED_CALL = "repeated_call"
    CONTRACT_UNREPAIRABLE = "contract_unrepairable"
    EMPTY_RESPONSES = "empty_responses"


#: Bir araç çağrısının tekrar tespitinde kullanılan imza.
#: (araç adı, normalize argümanlar, mutasyon çağı)
#:
#: Mutasyon çağı imzanın parçasıdır: çalışma alanı değiştikten SONRA aynı dosyayı
#: yeniden okumak meşrudur — içerik artık farklıdır. Değişiklik olmadan aynı okuma
#: ise ilerleme değildir.
CallSignature = tuple[str, str, int]


@dataclass(slots=True)
class TurnBudget:
    """Tur boyunca paylaşılan sayaçlar, sınırlar ve tekrar/ilerleme takibi."""

    clock: Clock
    max_model_calls: int
    max_verify_rounds: int
    max_empty_retries: int
    max_contract_repairs: int
    max_auto_continues: int
    max_idle_rounds: int
    #: Turun tamamı için üst süre sınırı. `None` ise süre sınırı uygulanmaz.
    total_timeout_s: float | None = None

    model_calls: int = 0
    verify_rounds: int = 0
    empty_retries: int = 0
    contract_repairs: int = 0
    auto_continues: int = 0
    #: Ardışık kaç turdur hiçbir ilerleme (başarılı araç / dosya dokunuşu) yok.
    idle_rounds: int = 0
    #: Başarılı her değiştirici araçtan sonra artar; tekrar imzasını tazeler.
    mutation_epoch: int = 0
    seen_calls: dict[CallSignature, int] = field(default_factory=dict)
    #: Bu turda BAŞARIYLA çalışmış araçlar: (ad, argümanlar, değiştirici mi).
    #
    # Eylem-kanıtı kapısı buraya bakar ve kanıt TUR GENELİNDE birikmek zorundadır.
    # Eskiden bu liste `_drive`'ın yerel durumundaydı; doğrulama düzeltmesi ve
    # öz-denetim `run_agent`'ı YENİDEN çağırdığı için iç içe tur taze bir durumla
    # başlıyor ve ana turun zaten kanıtladığı etkiyi baştan kanıtlaması isteniyordu.
    # Sonuç: model işi yapmış olmasına rağmen düzeltici tur "işlem tamamlanmadı"
    # diyordu. Aynı hata sınıfı bu modülün kuruluş gerekçesidir.
    successful_tool_evidence: list[tuple[str, dict[str, object], bool]] = field(
        default_factory=list
    )
    #: Tur durduysa sebebi; durmadıysa None.
    stop: BudgetStop | None = None

    _started_at: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self._started_at = self.clock.monotonic()

    # --- süre ------------------------------------------------------------- #

    @property
    def elapsed_s(self) -> float:
        return self.clock.monotonic() - self._started_at

    def remaining_s(self) -> float | None:
        """Kalan süre; sınır yoksa None. Negatif değer süre dolduğunu söyler."""
        if self.total_timeout_s is None:
            return None
        return self.total_timeout_s - self.elapsed_s

    def out_of_time(self) -> bool:
        remaining = self.remaining_s()
        return remaining is not None and remaining <= 0

    # --- sayaçlar --------------------------------------------------------- #

    def record_model_call(self) -> None:
        self.model_calls += 1

    @property
    def model_calls_exhausted(self) -> bool:
        return self.model_calls >= self.max_model_calls

    def take_empty_retry(self) -> bool:
        """Boş cevap için bir deneme hakkı al. Hak kalmadıysa False."""
        if self.empty_retries >= self.max_empty_retries:
            return False
        self.empty_retries += 1
        return True

    def take_contract_repair(self) -> bool:
        """Bozuk araç çağrısı için bir onarım hakkı al. Hak kalmadıysa False."""
        if self.contract_repairs >= self.max_contract_repairs:
            return False
        self.contract_repairs += 1
        return True

    def take_auto_continue(self) -> bool:
        """Yarım kalmış görünen cevap için bir "devam et" hakkı al."""
        if self.auto_continues >= self.max_auto_continues:
            return False
        self.auto_continues += 1
        return True

    def take_verify_round(self) -> bool:
        """Doğrulama kapısı için bir tur hakkı al."""
        if self.verify_rounds >= self.max_verify_rounds:
            return False
        self.verify_rounds += 1
        return True

    # --- tekrar ve ilerleme ------------------------------------------------ #

    def signature(self, name: str, encoded_arguments: str, *, mutating: bool) -> CallSignature:
        """Bir araç çağrısının tekrar imzasını üret.

        Değiştirici araçlarda çağ SIFIRLANIR: aynı yazma iki kez istendiyse bu her
        durumda tekrardır. Okuma araçlarında güncel çağ kullanılır, çünkü çalışma
        alanı değiştikten sonra aynı dosyayı yeniden okumak yeni bilgi getirir.
        """
        return (name, encoded_arguments, 0 if mutating else self.mutation_epoch)

    def count_call(self, signature: CallSignature) -> int:
        """İmzayı kaydet ve BU çağrıdan ÖNCE kaç kez görüldüğünü döndür."""
        seen = self.seen_calls.get(signature, 0)
        self.seen_calls[signature] = seen + 1
        return seen

    def record_mutation(self) -> None:
        """Başarılı bir değiştirici araç çalıştı: çalışma alanı ilerledi."""
        self.mutation_epoch += 1

    def record_failed_mutation(self) -> None:
        """Değiştirici bir çağrı DÜŞTÜ: modelin yeniden okumaya ihtiyacı var.

        Çalışma alanı değişmedi ama modelin BİLGİ durumu değişmek zorunda:
        `edit_file` "'old' bulunamadı" dediyse toparlanmanın tek yolu dosyayı
        yeniden okumaktır. Çağ ilerlemezse o okuma `TOOL_CALL_DUPLICATE` ile
        engelleniyor ve model çıkışsız kalıyordu — ölçüldü: edit düştü, model
        dosyayı yeniden okumak istedi, engellendi, tur "ilerleme yok" ile öldü.

        Değiştirici çağrıların imzası çağdan BAĞIMSIZDIR (daima 0), bu yüzden
        burada çağı ilerletmek aynı yazmanın tekrarını serbest bırakmaz.
        """
        self.mutation_epoch += 1

    def record_round(self, *, progressed: bool) -> None:
        """Bir araç turunu sonuçlandır: ilerleme oldu mu?

        İlerleme, ardışık boşta tur sayacını SIFIRLAR. Tek bir başarısız tur normaldir
        (model yanlış yolu dener, sonra düzeltir); ilerlemeyen turların ARDIŞIK olması
        modelin kendini toparlayamadığını gösterir.
        """
        self.idle_rounds = 0 if progressed else self.idle_rounds + 1

    @property
    def idle(self) -> bool:
        return self.idle_rounds >= self.max_idle_rounds

    # --- durdurma ---------------------------------------------------------- #

    def halt(self, reason: BudgetStop) -> BudgetStop:
        """Turu durdur ve sebebini kaydet. İlk sebep korunur."""
        if self.stop is None:
            self.stop = reason
        return reason

    @property
    def halted(self) -> bool:
        return self.stop is not None

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

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .protocols import Clock


class BudgetStop(Enum):
    """Turun neden durdurulduğu.

    Kullanıcıya gösterilecek METİN burada değildir; kod `ui` katmanında metne
    çevrilir (RULES.md "UI ve CLI": motor kullanıcı metni üretmez).
    """

    MODEL_CALLS = "model_calls"
    TOOL_ROUNDS = "tool_rounds"
    DEADLINE = "deadline"
    INACTIVITY = "inactivity"
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
    idle_timeout_s: float | None = None

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
    #: Değiştirici olarak üretilmiş imzalar.
    #
    # Çağ değerine bakarak ayırmak yanlıştı: tur başında çağ 0'dır ve OKUMA
    # imzaları da 0 taşır; geri alma sonrası unutma o yüzden okumaları da
    # siliyordu (test yakaladı).
    mutating_signatures: set[CallSignature] = field(default_factory=set)
    #: Bu turda DÜŞEN çağrıların imzaları. Başarılı bir değişiklikten sonra
    #: unutulurlar: düşme sebebi ortadan kalkmış olabilir.
    failed_signatures: set[CallSignature] = field(default_factory=set)
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
    _last_progress_at: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        now = self.clock.monotonic()
        self._started_at = now
        self._last_progress_at = now

    # --- süre ------------------------------------------------------------- #

    @property
    def elapsed_s(self) -> float:
        """Turun başlangıcından beri geçen mutlak süre."""
        return self.clock.monotonic() - self._started_at

    @property
    def idle_elapsed_s(self) -> float:
        """Son gerçek ilerlemeden beri geçen süre."""
        return self.clock.monotonic() - self._last_progress_at

    def remaining_s(self) -> float | None:
        """Mutlak hard-cap için kalan süre."""
        if self.total_timeout_s is None:
            return None
        return self.total_timeout_s - self.elapsed_s

    def idle_remaining_s(self) -> float | None:
        """İlerleme-yok sınırı için kalan süre."""
        if self.idle_timeout_s is None:
            return None
        return self.idle_timeout_s - self.idle_elapsed_s

    def next_timeout_s(self) -> float | None:
        """Hard ve idle deadline arasından önce dolacak olanı döndür."""
        limits = [
            value for value in (self.remaining_s(), self.idle_remaining_s()) if value is not None
        ]
        return min(limits) if limits else None

    def time_stop_reason(self) -> BudgetStop | None:
        """Süre sınırı aşıldıysa gerçek sebebi döndür."""
        remaining = self.remaining_s()
        if remaining is not None and remaining <= 0:
            return BudgetStop.DEADLINE

        idle_remaining = self.idle_remaining_s()
        if idle_remaining is not None and idle_remaining <= 0:
            return BudgetStop.INACTIVITY

        return None

    def out_of_time(self) -> bool:
        return self.time_stop_reason() is not None

    def record_progress(self) -> None:
        """Idle saatini tazele; turun mutlak başlangıcını değiştirme."""
        self._last_progress_at = self.clock.monotonic()

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

    def take_auto_continue(self, *, pending_todos: int = 0) -> bool:
        """Yarım kalmış görünen cevap için bir "devam et" hakkı al.

        Sabit tek hak, PLANLI işlerde yanlıştı: altı maddelik bir todo listesi
        yazan model tek dürtü alıp turu bitiriyordu — plan yapmak işi bitirmeye
        yaramıyordu. Bekleyen her madde bir hak daha açar; iş ilerledikçe
        maddeler kapanır ve hak kendiliğinden erir.

        Sonsuz değildir: tur bütçesi (model çağrısı, araç turu, süre) ve
        "ilerleme yok" kapısı üstte durmaya devam eder.
        """
        limit = self.max_auto_continues + max(0, pending_todos)
        if self.auto_continues >= limit:
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
        imza = (name, encoded_arguments, 0 if mutating else self.mutation_epoch)
        if mutating:
            self.mutating_signatures.add(imza)
        return imza

    def count_call(self, signature: CallSignature) -> int:
        """İmzayı kaydet ve BU çağrıdan ÖNCE kaç kez görüldüğünü döndür."""
        seen = self.seen_calls.get(signature, 0)
        self.seen_calls[signature] = seen + 1
        return seen

    def note_failed_call(self, signature: CallSignature) -> None:
        """Düşen çağrıyı işaretle; BAŞARILI bir değişiklikten sonra unutulacak.

        Hemen unutmak yanlış olurdu: arada hiçbir şey değişmeden aynı çağrıyı
        yinelemek gerçekten tekrardır ve engellenmelidir. Ama çalışma alanı
        gerçekten ilerlediyse aynı çağrı artık BAŞKA bir çağrıdır.
        """
        self.failed_signatures.add(signature)

    def forget_call(self, signature: CallSignature) -> None:
        """Bu çağrıyı YAPILMAMIŞ say.

        Tekrar koruması "bunu ZATEN YAPTIN" demektir; DÜŞEN bir çağrı hiçbir şey
        yapmamıştır. Ölçülen hata: `godot__create_scene` proje dosyası henüz
        yokken düştü, model `project.godot`'u yazdı, engel kalktı — ama aynı
        çağrı `TOOL_CALL_DUPLICATE` ile engellendi ve zincir öldü. Mesaj
        "çalışma alanında ilgili bir değişiklik olmadı" diyordu, oysa olmuştu.

        Değiştirici araçların imzası çağa DUYARSIZDIR (daima 0), bu yüzden
        koşullar düzelse bile imza asla değişmez; unutmak tek çıkış yoludur.
        Kalıcı olarak düşen bir çağrıyı "yinelenen hata" notu ve boşta-tur
        bütçesi yakalar.
        """
        # Kayıt TÜMDEN silinir, azaltılmaz: bu imzanın kaydedilen her denemesi
        # DÜŞTÜ. Bir azaltmak, iki kez denenmiş bir çağrıyı hâlâ engelli
        # bırakırdı (değiştirici araçlarda sınır zaten 1'dir).
        self.seen_calls.pop(signature, None)

    def forget_calls_touching(self, paths: Iterable[Path]) -> None:
        """Geri alınan dosyalara dokunan DEĞİŞTİRİCİ çağrıları yapılmamış say.

        Ölçüldü (7 Eylül, 42 görevlik set): adım `replace_range` ile doğru
        düzeltmeyi yazdı, kabuk çıktısı bile doğruladı; adım doğrulaması düşünce
        yazma geri alındı ve model AYNI doğru düzenlemeyi tekrar denediğinde
        `TOOL_CALL_DUPLICATE` ile engellendi. Engelin gerekçesi "çalışma alanında
        o zamandan beri ilgili bir değişiklik olmadı" idi — oysa değişiklik BİZ
        geri aldığımız için yoktu. Doğru hamle tam da tekrarlanması gereken
        hamleydi; görev bu ölü kilitle düştü.

        Yalnız değiştirici imzalar unutulur: onların imzası çağa duyarsızdır
        (daima 0) ve kendiliğinden asla çözülmez. Okuma çağrıları güncel çağı
        taşıdığı için zaten kendiliğinden serbest kalır.
        """
        aranan = {str(path) for path in paths}
        aranan |= {path.name for path in paths}
        for imza in [i for i in self.seen_calls if i in self.mutating_signatures]:
            if any(parca and parca in imza[1] for parca in aranan):
                self.seen_calls.pop(imza, None)
                self.failed_signatures.discard(imza)

    def record_mutation(self) -> None:
        """Başarılı bir değiştirici araç çalıştı: çalışma alanı ilerledi.

        Daha önce DÜŞEN çağrılar burada unutulur: engelleri kalkmış olabilir.
        Ölçülen hata: `godot__create_scene` proje dosyası yokken düştü, model
        `project.godot`'u yazdı, engel kalktı — ama aynı çağrı
        `TOOL_CALL_DUPLICATE` ile engellendi ve zincir öldü.
        """
        self.mutation_epoch += 1
        for imza in self.failed_signatures:
            self.forget_call(imza)
        self.failed_signatures.clear()

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
        """Bir araç turunu sonuçlandır ve gerçek ilerlemeyi kaydet."""
        if progressed:
            self.idle_rounds = 0
            self.record_progress()
        else:
            self.idle_rounds += 1

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

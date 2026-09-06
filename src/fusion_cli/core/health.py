"""Sağlayıcı sağlığı — circuit breaker ve güvenilirlik skoru.

Bu durum TUR ÖTESİDİR: bir modelin arka arkaya başarısız olması sonraki turları da
ilgilendirir. Bu yüzden modül-global değil, oturuma bağlı bir `HealthRegistry`'de
tutulur ve enjekte edilir (RULES.md: gizli global state yok, zaman `Clock`'tan gelir).

İki bağımsız mekanizma:

- **Circuit breaker**: bir model arka arkaya `failure_threshold` kez başarısız olursa
  devre AÇILIR ve `cooldown_s` boyunca o model ATLANIR (hızlı başarısızlık → zincir
  sıradaki modele geçer). Süre dolunca YARI-AÇIK bir deneme yapılır; başarılıysa devre
  kapanır, değilse yeniden açılır. Amaç: ölü bir modeli her turda yeniden yoklayıp
  kullanıcıyı bekletmemek.
- **Güvenilirlik skoru**: son-ağırlıklı (EWMA) başarı oranı. "Hatasız sağlayıcı" sabit
  bir sıfat değildir (master prompt §8.1); kısa süreli arıza modeli kalıcı olarak kötü
  saymaz, skor zamanla toparlar.
"""

from __future__ import annotations

from enum import Enum

from .clock import SystemClock
from .protocols import Clock


class CircuitPhase(Enum):
    """Circuit breaker'ın durumu."""

    #: Çağrılar geçer.
    CLOSED = "closed"
    #: Çağrılar atlanır (cooldown sürüyor).
    OPEN = "open"
    #: Cooldown doldu; tek bir deneme çağrısına izin verilir.
    HALF_OPEN = "half_open"


#: Kota hatasında soğumanın taban çarpanı ve üst sınırı.
#
# Taban 3'tür: sağlayıcı kotası saniyeler değil dakikalar ölçeğinde toparlanır,
# ama ilk denemeyi de saatlerce ertelememek gerekir. Üst sınır 8'dir; ötesi,
# oturum boyunca modeli fiilen dışlamak demektir.
RATE_LIMIT_BASE_MULTIPLIER = 3.0
RATE_LIMIT_MAX_MULTIPLIER = 8


class ModelHealth:
    """Tek bir modelin devre durumu + güvenilirlik skoru.

    Durumsaldır (mutable); `CostTracker` gibi biriktiren bir kayıttır. Değeri
    `record` besler, `allow` okur.
    """

    def __init__(
        self,
        *,
        failure_threshold: int,
        cooldown_s: float,
        alpha: float,
        clock: Clock,
        initial_score: float = 1.0,
    ) -> None:
        self._threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._alpha = alpha
        self._clock = clock
        self._phase = CircuitPhase.CLOSED
        self._consecutive_failures = 0
        #: Art arda gelen kota hatası sayısı; geri çekilmenin katsayısıdır.
        self._rate_limit_streak = 0
        self._opened_at = 0.0
        #: Yeni model iyimser başlar: tek bir geçici arıza onu dışlamasın.
        self._score = initial_score
        self._samples = 0
        #: Başarılı çağrıların son-ağırlıklı ortalama gecikmesi (ms). 0 = veri yok.
        self._avg_latency_ms = 0.0

    @property
    def phase(self) -> CircuitPhase:
        return self._phase

    @property
    def avg_latency_ms(self) -> float:
        """Son-ağırlıklı ortalama gecikme (ms); veri yoksa 0."""
        return self._avg_latency_ms

    @property
    def score(self) -> float:
        """Son-ağırlıklı başarı oranı [0, 1]."""
        return self._score

    @property
    def samples(self) -> int:
        return self._samples

    def allow(self) -> bool:
        """Bu modele çağrı yapılabilir mi? Cooldown dolduysa yarı-açığa geçer."""
        if self._phase is not CircuitPhase.OPEN:
            return True
        if self._clock.monotonic() - self._opened_at >= self._current_cooldown():
            self._phase = CircuitPhase.HALF_OPEN
            return True
        return False

    def _current_cooldown(self) -> float:
        """Kota gerilimi varsa artan geri çekilme, yoksa normal soğuma.

        Kota/hız sınırı geçici bir arıza değildir: sağlayıcı "şimdi olmaz" diyor ve
        aynı soğumayla hemen dönmek turu yakar (ölçüldü, web koşuları). Artış
        katlanarak ilerler ama ÜST SINIRI vardır: sınırsız bekleme, sağlayıcı
        toparlansa bile modeli oturum boyunca dışlardı.
        """
        if not self._rate_limit_streak:
            return self._cooldown_s
        carpan = min(2 ** (self._rate_limit_streak - 1), RATE_LIMIT_MAX_MULTIPLIER)
        return float(self._cooldown_s * RATE_LIMIT_BASE_MULTIPLIER * carpan)

    def record(self, ok: bool, *, latency_ms: int = 0, rate_limited: bool = False) -> None:
        """Bir çağrının sonucunu işle: skoru + gecikmeyi güncelle, devreyi aç/kapat."""
        self._score = self._alpha * (1.0 if ok else 0.0) + (1.0 - self._alpha) * self._score
        self._samples += 1
        if ok:
            if latency_ms > 0:
                # Yalnızca başarılı çağrının gecikmesi ölçülür; ilk ölçüm doğrudan alınır.
                prev = self._avg_latency_ms or float(latency_ms)
                self._avg_latency_ms = self._alpha * latency_ms + (1.0 - self._alpha) * prev
            self._consecutive_failures = 0
            # Başarılı çağrı kota gerilimini de sıfırlar: sağlayıcı toparlandıysa
            # onu eski cezasıyla bekletmek ölçülen duruma aykırıdır.
            self._rate_limit_streak = 0
            self._phase = CircuitPhase.CLOSED
            return
        self._consecutive_failures += 1
        if rate_limited:
            # Eşik BEKLENMEZ: sağlayıcı zaten kapasitesi olmadığını söyledi. Aynı
            # kapıya art arda çarpmak tur bütçesini yakar.
            self._rate_limit_streak += 1
            self._phase = CircuitPhase.OPEN
            self._opened_at = self._clock.monotonic()
            return
        # Yarı-açıkken bir başarısızlık devreyi hemen yeniden açar; kapalıyken ancak
        # eşik dolunca açılır.
        if self._phase is CircuitPhase.HALF_OPEN or self._consecutive_failures >= self._threshold:
            self._phase = CircuitPhase.OPEN
            self._opened_at = self._clock.monotonic()


class HealthRegistry:
    """Model kimliği → `ModelHealth`. Oturum boyunca tek örnek, enjekte edilir."""

    def __init__(
        self,
        *,
        failure_threshold: int,
        cooldown_s: float,
        alpha: float,
        clock: Clock | None = None,
    ) -> None:
        self._threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._alpha = alpha
        self._clock = clock or SystemClock()
        self._entries: dict[str, ModelHealth] = {}

    def for_model(self, model_id: str) -> ModelHealth:
        """Modelin sağlık kaydını getir; yoksa oluştur (tembel)."""
        entry = self._entries.get(model_id)
        if entry is None:
            entry = ModelHealth(
                failure_threshold=self._threshold,
                cooldown_s=self._cooldown_s,
                alpha=self._alpha,
                clock=self._clock,
            )
            self._entries[model_id] = entry
        return entry

    def snapshot(self) -> tuple[tuple[str, ModelHealth], ...]:
        """Görüntüleme için (model_id, health) çiftleri; skora göre artan sırada."""
        return tuple(sorted(self._entries.items(), key=lambda pair: pair[1].score))

    def reset(self) -> None:
        """Tüm sağlık kayıtlarını temizle (devreleri kapat, skorları sıfırla)."""
        self._entries.clear()

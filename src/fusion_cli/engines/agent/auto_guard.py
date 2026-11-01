"""Otomatik kip denetçisinin oturum durumu: engel sayaçları, kip düşüşü, önbellek (P-011).

Politika her turda (masaüstünde her çağrıda) yeniden kurulur; sayaçlar turlar arasında
yaşamalı. Bu yüzden durum, oturum boyu yaşayan `ApprovalMemory`'nin içindedir ve motor
ona `AgentDeps.auto_review` üzerinden ulaşır.

Engel = denetçi MODELİNİN "riskli" kararı. Kurallı yedeğin (model yok) kararı sayılmaz:
çevrimdışı oturum eski davranışı korur, birkaç riskli komut yüzünden Manuel'e düşmez.
Üst üste `AUTO_REVIEW_CONSECUTIVE_LIMIT` ya da toplam `AUTO_REVIEW_TOTAL_LIMIT` engelde
kip düşer: sahibin bağladığı `on_fallback` oturum kipini Manuel'e çeker; bağlanmadıysa
(`fusion run`) o anki Otomatik politika kendini Manuel gibi davranmaya çevirir.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...core.auto_review import (
    AUTO_REVIEW_CACHE_LIMIT,
    AUTO_REVIEW_CONSECUTIVE_LIMIT,
    AUTO_REVIEW_MODEL_FAILURE_LIMIT,
    AUTO_REVIEW_RECENT_LIMIT,
    AUTO_REVIEW_TOTAL_LIMIT,
    AutoReviewSnapshot,
    ReviewOutcome,
    ReviewSource,
    ReviewVerdict,
)

if TYPE_CHECKING:  # yalnız tip: `approval` bu modülü içe aktarır
    from .approval import ApprovalRequest

#: Kip düşüşünün gerekçe metinleri (olay, durum ekranı).
TRIP_CONSECUTIVE = "denetçi üst üste {count} çağrıyı riskli buldu"
TRIP_TOTAL = "denetçi bu oturumda toplam {count} çağrıyı riskli buldu"


class AutoReviewState:
    """Oturum boyu denetçi durumu. Tek iş parçacığında (olay döngüsünde) kullanılır."""

    def __init__(self, remembered: Callable[[ApprovalRequest], bool] | None = None) -> None:
        #: Bu çağrıya oturum izni zaten verildi mi? Verildiyse model boşuna çağrılmaz.
        self.remembered = remembered
        self.consecutive = 0
        self.total = 0
        #: Kaç kez Manuel'e düşüldü; Otomatik politika kurulduğu andaki değeri saklar.
        self.trips = 0
        self.model_failures = 0
        self.fell_back = False
        self.last_trip_reason = ""
        self._recent: deque[ReviewOutcome] = deque(maxlen=AUTO_REVIEW_RECENT_LIMIT)
        self._cache: OrderedDict[str, ReviewOutcome] = OrderedDict()
        #: Kip düşünce oturum kipini Manuel'e çeken geri çağrı (sahip bağlar).
        self.on_fallback: Callable[[], None] | None = None
        #: Bypass kullanılabilir oturum mu (#52; sahip bağlar): plan kipinde sınıflandırıcı yok.
        self.plan_bypass: Callable[[], bool] | None = None

    @property
    def model_unavailable(self) -> bool:
        """Model üst üste başarısız oldu: oturumun kalanında yalnız kurallar."""
        return self.model_failures >= AUTO_REVIEW_MODEL_FAILURE_LIMIT

    def cached(self, key: str) -> ReviewOutcome | None:
        found = self._cache.get(key)
        if found is not None:
            self._cache.move_to_end(key)
        return found

    def remember(self, key: str, outcome: ReviewOutcome) -> None:
        """Yalnız model kararı önbelleğe girer; kurallı yedek her seferinde yeniden denenir."""
        if outcome.source is not ReviewSource.MODEL:
            return
        self._cache[key] = outcome
        self._cache.move_to_end(key)
        while len(self._cache) > AUTO_REVIEW_CACHE_LIMIT:
            self._cache.popitem(last=False)

    def note_model_failure(self) -> None:
        self.model_failures += 1

    def note_model_success(self) -> None:
        self.model_failures = 0

    def record(self, outcome: ReviewOutcome) -> str | None:
        """Kararı say; eşik aşıldıysa kipi düşür ve gerekçeyi döndür (yoksa None)."""
        self._recent.append(outcome)
        if outcome.source is ReviewSource.RULE:
            return None
        if outcome.verdict is ReviewVerdict.SAFE:
            self.consecutive = 0
            return None
        self.consecutive += 1
        self.total += 1
        if self.consecutive >= AUTO_REVIEW_CONSECUTIVE_LIMIT:
            return self._trip(TRIP_CONSECUTIVE.format(count=self.consecutive))
        if self.total >= AUTO_REVIEW_TOTAL_LIMIT:
            return self._trip(TRIP_TOTAL.format(count=self.total))
        return None

    def _trip(self, reason: str) -> str:
        self.trips += 1
        self.fell_back = True
        self.last_trip_reason = reason
        self.consecutive = 0
        self.total = 0
        if self.on_fallback is not None:
            self.on_fallback()
        return reason

    def resume(self) -> None:
        """Kullanıcı Otomatik'e döndü: sayaçlar ve model hata sayacı sıfırlanır."""
        self.fell_back = False
        self.consecutive = 0
        self.total = 0
        self.model_failures = 0

    def acknowledge_auto(self) -> None:
        """Otomatik kip yeniden seçildi (yeni politika kuruldu): düşüş uyarısı kalkar."""
        self.fell_back = False

    def snapshot(self) -> AutoReviewSnapshot:
        return AutoReviewSnapshot(
            consecutive=self.consecutive,
            total=self.total,
            trips=self.trips,
            model_failures=self.model_failures,
            fell_back=self.fell_back,
            last_trip_reason=self.last_trip_reason,
            recent=tuple(self._recent),
        )

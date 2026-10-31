"""Otomatik kip denetçisi (risk sınıflandırıcısı) — saf tipler ve eşikler (P-011).

Claude Code'un auto mode'u kural ve salt-okunur denetiminden sonra belirsiz eylemi ayrı bir
sınıflandırıcı modele sorar; üst üste 3 ya da toplam 20 engelde manuel kipe düşer. Fusion'da
karşılığı: Otomatik kipte SORULACAK çağrıyı küçük/hızlı rol modeli "güvenli/riskli" diye
sınıflandırır; güvenliyse sorulmaz, riskliyse sorulur. Eşikler Claude'daki gibi sabittir.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AutoClassifierMode(Enum):
    """`runtime.auto_classifier`: denetçinin hangi çağrılara bakacağı.

    off       eski davranış: yalnız kurallar (`auto_policy`); model çağrılmaz
    ask_only  kuralların SORACAĞI çağrı sınıflandırılır; güvenliyse sorulmaz
    on        ek olarak kuralların geçirdiği, salt okunur olmayan her kabuk komutu da
              sınıflandırılır (proje betikleri dahil); riskli bulunursa sorulur
    """

    OFF = "off"
    ASK_ONLY = "ask_only"
    ON = "on"

    @classmethod
    def _missing_(cls, value: object) -> AutoClassifierMode | None:
        """YAML 1.1 tırnaksız `off`/`on` mantıksal değer okunur; kullanıcı niyeti metindir."""
        if value is False:
            return cls.OFF
        if value is True:
            return cls.ON
        return None


class ReviewVerdict(Enum):
    """Denetçinin kararı."""

    SAFE = "guvenli"
    RISKY = "riskli"


class ReviewSource(Enum):
    """Kararın nereden geldiği; denetim günlüğü ve arayüz bunu gösterir."""

    MODEL = "model"
    #: Model yok/erişilemedi/cevap bozuk: kuralların kararı geçerli (kurallı yedek).
    RULE = "kural"
    #: Aynı çağrı bu oturumda zaten sınıflandırıldı; model yeniden çağrılmadı.
    CACHE = "onbellek"


#: Üst üste bu kadar "riskli" model kararı → oturum Manuel kipe düşer (Claude: 3).
AUTO_REVIEW_CONSECUTIVE_LIMIT = 3
#: Oturumda toplam bu kadar "riskli" model kararı → Manuel kipe düşer (Claude: 20).
AUTO_REVIEW_TOTAL_LIMIT = 20
#: Üst üste bu kadar model hatası → oturumun kalanında yalnız kurallar (çevrimdışı yedek).
#: Her riskli komutta zaman aşımını beklememek için; `/auto-mode devam` sayacı sıfırlar.
AUTO_REVIEW_MODEL_FAILURE_LIMIT = 3
#: Durum ekranında tutulan son karar sayısı.
AUTO_REVIEW_RECENT_LIMIT = 20
#: Oturum içi karar önbelleğinin en fazla girdisi.
AUTO_REVIEW_CACHE_LIMIT = 128
#: Modele gönderilen kullanıcı mesajı sayısı ve her birinin karakter sınırı.
AUTO_REVIEW_INTENT_MESSAGES = 3
AUTO_REVIEW_INTENT_CHARS = 800
#: Modele gönderilen araç argümanlarının karakter sınırı.
AUTO_REVIEW_ARGS_CHARS = 2000
#: Kartta/olayda gösterilen komut özetinin karakter sınırı.
AUTO_REVIEW_SUMMARY_CHARS = 160


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    """Tek bir sınıflandırma sonucu."""

    tool: str
    verdict: ReviewVerdict
    reason: str
    source: ReviewSource
    #: Kısaltılmış komut/hedef (kartta ve durum ekranında).
    summary: str


@dataclass(frozen=True, slots=True)
class AutoReviewSnapshot:
    """Denetçinin anlık durumu: `/auto-mode`, `fusion auto-mode durum`, `oto.durum`."""

    consecutive: int
    total: int
    trips: int
    model_failures: int
    fell_back: bool
    last_trip_reason: str
    recent: tuple[ReviewOutcome, ...]

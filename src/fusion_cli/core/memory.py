"""Kalıcı bellek sözleşmeleri.

Motorlar ChromaDB'yi tanımaz; yalnızca buradaki protokolleri görür. Bu sayede
depolama arkası değiştirilebilir, testte sahte verilebilir ve `--no-memory` gibi
bir seçenek "hiçbir şey yapmayan" bir uygulama vererek karşılanır — motor kodunda
`if bellek varsa` dalları oluşmaz.

Üç ayrı bellek vardır ve bilinçli olarak ayrıdır:

- **Performans belleği** — hangi model hangi görev tipinde iyiydi. Fusion motorunun
  aday sıralamasını zamanla iyileştirir.
- **Ders belleği** — agent'ın geçmiş turlardan çıkardığı kaçınılacak/uygulanacak
  dersler. Benzer bir görevde sistem promptuna geri enjekte edilir.
- **Kod indeksi** — projenin anlamsal araması. "X nerede yapılıyor?" sorusunu
  grep'ten iyi cevaplar.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class LessonKind(Enum):
    """Dersin türü. Hatalar geri çağırmada öne alınır: kaçınmak daha kritiktir."""

    MISTAKE = "mistake"
    SUCCESS = "success"


class LessonSource(Enum):
    """Dersin nereden geldiği."""

    LEARNED = "learned"  # bir oturumdan çıkarıldı
    SEED = "seed"  # küratörlü başlangıç bilgisi
    MANUAL = "manual"  # kullanıcı elle öğretti


#: Bir dersin başlangıç güveni. Yeni ve eski (alan taşınmadan yazılmış) kayıtlar
#: bu değerle okunur: ders bir kez denenir, sonucuna göre güveni artar/azalır.
DEFAULT_LESSON_CONFIDENCE = 1.0


@dataclass(frozen=True, slots=True)
class Lesson:
    """Gelecekte davranışı değiştirecek somut bir ders.

    `confidence`, `success_count` ve `failure_count` dersin öz-düzeltmesini taşır:
    enjekte edildiği tur başarısızsa güven düşer, başarılıysa artar. Güveni eşiğin
    altına düşen ders artık enjekte edilmez (yerel zehirlenmeye karşı koruma).
    """

    text: str
    kind: LessonKind
    #: Dersin çıktığı görev bağlamı. Anlamsal geri çağırmada kullanılır.
    task: str = ""
    source: LessonSource = LessonSource.LEARNED
    #: Dersin güncel güveni (0..1). Eşiğin altındaki ders enjekte edilmez.
    confidence: float = DEFAULT_LESSON_CONFIDENCE
    #: Enjekte edildiği turların kaçında iş başarıyla bitti.
    success_count: int = 0
    #: Enjekte edildiği turların kaçında iş başarısız oldu.
    failure_count: int = 0
    #: İsteğe bağlı görev-türü kapsamı (bugfix/refactor/…); boş = her kapsam.
    scope: str = ""
    #: İsteğe bağlı tetikleyici ipucu; boş = serbest.
    trigger: str = ""


class Feedback(Enum):
    """Kullanıcının bir sonuca verdiği geri bildirim ve skor etkisi."""

    GOOD = "good"
    BAD = "bad"
    REVISE = "revise"

    @property
    def delta(self) -> float:
        return {"good": 0.10, "bad": -0.10, "revise": -0.20}[self.value]


@dataclass(frozen=True, slots=True)
class Outcome:
    """Bir modelin tek bir görevdeki performans kaydı."""

    task: str
    task_type: str
    model_name: str
    #: Hakem puanı, 0..1.
    score: float
    latency_ms: int
    tokens: int
    won: bool


@dataclass(frozen=True, slots=True)
class ModelStats:
    """Bir modelin toplam performansı (gösterim için)."""

    model: str
    samples: int
    avg_score: float
    wins: int
    avg_latency_ms: int


@dataclass(frozen=True, slots=True)
class CodeMatch:
    """Kod indeksinden dönen anlamsal eşleşme."""

    path: str
    start_line: int
    end_line: int
    snippet: str


@dataclass(frozen=True, slots=True)
class IndexStats:
    """Artımlı indeksleme sonucu."""

    total: int
    added: int
    removed: int

    @property
    def unchanged(self) -> int:
        return self.total - self.added


class PerformanceMemory(Protocol):
    """Model performans geçmişi."""

    def record(self, outcome: Outcome) -> None: ...

    def best_model(self, task_type: str) -> str | None:
        """Görev tipinde geçmişi en iyi model adı; veri yoksa None."""
        ...

    def apply_feedback(self, task_type: str, model_name: str, feedback: Feedback) -> int:
        """Geri bildirimi en yeni kayda uygula; etkilenen kayıt sayısını döndür."""
        ...

    def stats(self) -> tuple[ModelStats, ...]: ...


class LessonMemory(Protocol):
    """Agent'ın öğrendiği dersler."""

    def add(self, lesson: Lesson) -> bool:
        """Dersi kaydet. Zaten varsa False döner (tekilleştirme)."""
        ...

    def recall(self, task: str, limit: int = 4, *, scope: str | None = None) -> tuple[Lesson, ...]:
        """Göreve YETERİNCE BENZER ve güveni eşiğin üstünde dersleri getir.

        `scope` verilirse yalnızca o görev-türü kapsamındaki (ya da kapsamsız/genel)
        dersler döner. Geri çağırma hibrittir: embedding + lexical (BM25) birleşir.
        """
        ...

    def reinforce(self, texts: tuple[str, ...], *, success: bool) -> int:
        """Enjekte edilen derslerin güvenini turun sonucuna göre güncelle.

        `success=False` güveni düşürür ve `failure_count`'u artırır; `True` tersi.
        Güncellenen ders sayısını döndürür.
        """
        ...

    def all(self) -> tuple[Lesson, ...]: ...

    def count(self) -> int: ...


class CodeIndex(Protocol):
    """Projenin anlamsal kod indeksi."""

    def search(self, query: str, limit: int = 6) -> tuple[CodeMatch, ...]: ...

    def reindex(self) -> IndexStats:
        """Artımlı indeksle: yalnızca değişen parçalar yeniden gömülür."""
        ...

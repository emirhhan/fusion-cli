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

from .repair_ledger import FailureOrigin


class LessonKind(Enum):
    """Dersin türü. Hatalar geri çağırmada öne alınır: kaçınmak daha kritiktir."""

    MISTAKE = "mistake"
    SUCCESS = "success"


class LessonSource(Enum):
    """Dersin nereden geldiği."""

    LEARNED = "learned"  # bir oturumdan çıkarıldı
    SEED = "seed"  # küratörlü başlangıç bilgisi
    MANUAL = "manual"  # kullanıcı elle öğretti
    TEACHER = "teacher"  # web öğretmene danışmadan (Faz 4, Görev 3)


#: Bir dersin başlangıç güveni. Yeni ve eski (alan taşınmadan yazılmış) kayıtlar
#: bu değerle okunur: ders bir kez denenir, sonucuna göre güveni artar/azalır.
DEFAULT_LESSON_CONFIDENCE = 1.0

#: Kendi belleği olan (`memory:` alanlı) alt ajanın derslerine konan etiket öneki (P-055).
#: Bu etiketi taşıyan ders yalnız aynı etiketle (aynı ajan) geri çağrılır.
AGENT_LESSON_TAG_PREFIX = "ajan:"


def agent_lesson_tag(agent: str) -> str:
    """`ajan:<ad>` etiketi."""
    return f"{AGENT_LESSON_TAG_PREFIX}{agent}"


def visible_to(lesson_tags: tuple[str, ...], requested: tuple[str, ...]) -> bool:
    """Ders bu çağrıyı yapan ajana görünür mü? Ajan etiketsiz ders herkese görünür."""
    owners = {tag for tag in lesson_tags if tag.startswith(AGENT_LESSON_TAG_PREFIX)}
    return not owners or bool(owners & set(requested))


@dataclass(frozen=True, slots=True)
class Lesson:
    """Gelecekte davranışı değiştirecek somut bir ders.

    Eski çağrıda enjekte edilen turun sonucu güveni etkiler. Atıflı çağrıda
    yalnız açık kullanım ve doğrulanmış sonuç kanıtı güveni değiştirir.
    Eşik altındaki ders geri çağırmadan elenir.
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
    #: Dersin ait olduğu TEKNOLOJİLER (godot, python, node…) ve MCP sunucuları.
    #:
    #: `workspace` ile arasındaki fark ölçülerek ortaya çıktı: 20 koşuda 38 Godot
    #: dersi öğrenildi, ama yeni bir Godot klasöründe hiçbiri hatırlanmadı —
    #: workspace süzgeci hepsini eledi. Oysa "Godot MCP'de `res://` kullanma"
    #: dersi öğrenildiği KLASÖRE değil öğrenildiği TEKNOLOJİYE aittir.
    #:
    #: Üç katman olur: etiketsiz ve workspace'siz ders GENEL, workspace'li ders
    #: O PROJEYE özel ("auth modülü src/auth altında"), etiketli ders ise aynı
    #: teknolojideki HER projede geçerli. Alan taşınmadan önce yazılmış kayıtlar
    #: boş okunur; göç gerekmez, eski davranış korunur.
    tags: tuple[str, ...] = ()
    #: Dersin ait olduğu proje kökü. BOŞ = genel (her projede geçerli).
    #:
    #: "auth modülü src/auth altında" gibi bir gözlem yalnızca öğrenildiği projede
    #: doğrudur; başka projede hatırlanması modeli yanlış yere yönlendirir. Hazır
    #: yordamsal dersler ("dosyayı değiştirmeden önce oku") boş bırakılır ve her
    #: projede geçerli kalır. Alan taşınmadan önce yazılmış kayıtlar da boş okunur,
    #: yani göç gerekmez ve eski dersler genel sayılır.
    workspace: str = ""
    #: Ders, dış içerik (web/tarayıcı/MCP/klonlanan site) okunan turdan çıktı ve henüz
    #: dış içeriksiz BAŞARILI bir turda doğrulanmadı. Dış metin kalıcı belleğe zehir
    #: sokabilir (MINJA); bu ders düşük güvenle başlar, dış içerikli başarıyla güven
    #: kazanmaz ve istemde "dış kaynaklı" etiketiyle gösterilir. Alan taşınmadan önce
    #: yazılmış kayıtlar False okunur (göç gerekmez).
    external: bool = False
    #: Depodaki mevcut kimlik; eski kayıtlarda depodan okununca doldurulur.
    id: str = ""
    subject_key: str = ""
    applies_to: tuple[str, ...] = ()
    version: str = ""
    supersedes: tuple[str, ...] = ()
    verified_at: str = ""
    quarantined: bool = False
    #: Boş değer bilinmeyen kökendir; geliştirme veya kör veri diye uydurulmaz.
    source_split: str = ""
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LessonRecallPolicy:
    """Çağıranın açıkça etkinleştirdiği bağlam ve çelişki süzgeçleri."""

    subject_key: str = ""
    applies_to: tuple[str, ...] = ()
    version: str = ""
    source_split: str = ""
    conflict_quarantine: bool = False


@dataclass(frozen=True, slots=True)
class RoutineSpec:
    """Mevcut playbook/plan kimliğiyle öneriye taşınan doğrulama tanımı."""

    routine_id: str
    description: str
    input_schema: str
    preconditions: tuple[str, ...]
    checks: tuple[str, ...]
    source_digest: str = ""


@dataclass(frozen=True, slots=True)
class RoutineObservation:
    """Rutin koşumunun bağımsız doğrulanmış sonucu; içerik yerine kanıt referansı."""

    run_id: str
    success: bool
    verified: bool
    evidence_refs: tuple[str, ...] = ()
    source_split: str = ""
    failure_origin: FailureOrigin = FailureOrigin.PRODUCT


@dataclass(frozen=True, slots=True)
class SkillProposal:
    """Yalnız öneri kaydıdır; beceri kurulumu veya çalıştırma yetkisi taşımaz."""

    id: str
    routine: RoutineSpec
    source_split: str
    observations: tuple[RoutineObservation, ...]


class SkillProposalMemory(Protocol):
    """Doğrulanmış rutin önerilerinin asenkron kalıcılık sözleşmesi."""

    async def observe(
        self,
        routine: RoutineSpec,
        observation: RoutineObservation,
    ) -> SkillProposal | None: ...

    async def list(self, *, source_split: str | None = None) -> tuple[SkillProposal, ...]: ...

    async def get(self, proposal_id: str) -> SkillProposal | None: ...


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
    #: Parça tavanına takıldı: sonraki dosyalar indekste YOK, arama onları bulamaz.
    truncated: bool = False
    #: Yazılamayan parça sayısı (bellek kilidi, zaman aşımı ya da depo hatası). 0 değilse
    #: indeks EKSİKTİR; `added`/`removed` yalnız gerçekten yazılanları sayar.
    failed: int = 0

    @property
    def unchanged(self) -> int:
        return max(self.total - self.added - self.failed, 0)


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

    def recall(
        self,
        task: str,
        limit: int = 4,
        *,
        scope: str | None = None,
        workspace: str | None = None,
        tags: tuple[str, ...] = (),
        policy: LessonRecallPolicy | None = None,
    ) -> tuple[Lesson, ...]:
        """Göreve YETERİNCE BENZER ve güveni eşiğin üstünde dersleri getir.

        `scope` verilirse yalnızca o görev-türü kapsamındaki (ya da kapsamsız/genel)
        dersler döner. Geri çağırma hibrittir: embedding + lexical (BM25) birleşir.

        `workspace` verilirse başka projelerde öğrenilmiş dersler ELENİR; kapsamsız
        (genel yordamsal) dersler her projede kalır.
        """
        ...

    def reinforce(
        self,
        texts: tuple[str, ...],
        *,
        success: bool,
        external_turn: bool = False,
        feedback_reason: str | None = None,
        evidence_refs: tuple[str, ...] = (),
        used: bool | None = None,
        failure_origin: FailureOrigin = FailureOrigin.PRODUCT,
        verified_at: str = "",
        lesson_ids: tuple[str, ...] | None = None,
    ) -> int:
        """Enjekte edilen derslerin güvenini turun sonucuna göre güncelle.

        `success=False` güveni düşürür ve `failure_count`'u artırır; `True` tersi.
        `external_turn=True`: tur dış içerik okudu; "dış kaynaklı" ders bu başarıyla
        doğrulanmış sayılmaz (çağıranlar bayrağı YALNIZ True iken geçer).
        `feedback_reason` ve diğer atıf alanları verildiğinde kullanım/kanıt
        eksikse değişiklik yapılmaz; provider/infra kesintisi cezalandırılmaz.
        Güncellenen ders sayısını döndürür.
        """
        ...

    def set_quarantined(self, lesson_ids: tuple[str, ...], *, quarantined: bool) -> int:
        """Mevcut depo kimlikleriyle geri alınabilir karantina uygula."""
        ...

    def retag_from_workspace(self) -> int:
        """Etiketsiz derslere, kayıtlı proje kökünden teknoloji etiketi ver."""
        ...

    def forget(self, texts: tuple[str, ...]) -> int:
        """Verilen metinlere birebir uyan dersleri belleğe SİL; silinen sayısını döndür.

        Metinle eşleşir, kimlikle değil — `add` zaten metni tekilleştiriyor ve
        `reinforce` de aynı yolu kullanıyor; ikinci bir kimlik kavramı açmak aynı
        işi yapan ikinci bir yol olurdu.

        Silme gerekli çünkü güven decay'i yetmiyor: bozuk bir turdan çıkmış ders
        eşiğin altına düşse bile depoda durur, geri çağırma havuzunu şişirir ve
        sıralamada gerçek dersleri geriye iter.
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

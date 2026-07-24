"""Tiplenmiş yapılandırma nesneleri.

DİKKAT — bu dosyadaki alanlara varsayılan değer YAZILMAZ. Varsayılanların tek kaynağı
`defaults.yaml`'dır. Eski projede aynı varsayılan hem kodda hem dosyada duruyordu ve
ikisi zamanla ayrıştı (ör. timeout kodda 120, dosyada 45). Alanları zorunlu bırakmak
bu sapmayı derleme/yükleme anında imkânsız kılar: `defaults.yaml` bir alanı unutursa
yapılandırma hiç yüklenmez ve test kırılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core.types import ModelSpec


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Çalışma zamanı davranışı."""

    request_timeout_s: float
    max_retries: int
    temperature: float
    max_tokens: int
    #: Hakem için sıkı son tarih. Aşılırsa sezgisel kazanan seçilir, tur durmaz.
    judge_timeout_s: float
    #: Hakem bütçesi. Reasoning modelleri düşünme + JSON'u buraya sığdırmalıdır.
    judge_max_tokens: int
    #: Bu sayının altında başarılı aday kalırsa tur cevapsız biter.
    min_successful_candidates: int
    #: Yeterli cevap geldikten sonra yavaş adaylara tanınan ek süre.
    straggler_grace_s: float
    #: İlk cevaptan itibaren adaylar için mutlak üst sınır.
    candidate_hard_cap_s: float
    #: Hakem seçtikten sonra tüm cevapları tek üstün cevapta birleştir.
    synthesis: bool
    #: Agent modunda ardışık araç turu üst sınırı.
    agent_max_steps: int
    #: Agent: tur bitince denetçi model sonucu kontrol eder, gerekirse düzeltir.
    self_review: bool
    #: Agent: araç hatasında modele "farklı yaklaş" notu enjekte edilir.
    reflexion: bool
    #: Agent: her görevden ders çıkarılır ve benzer görevlerde promptta hatırlatılır.
    lessons: bool
    #: Agent: kod değiştiren tur sonrası çalıştırılacak doğrulama komutları (ruff/mypy/
    #: pytest ya da alt kümesi). Boş = doğrulama kapalı; sonuç ders güvenini besler.
    verification_commands: tuple[str, ...] = ()
    #: Agent: istek bir playbook'u tetiklerse serbest döngü yerine deterministik akış
    #: çalışır (daha az model çağrısı). Varsayılan kapalı: mevcut davranış korunur.
    playbooks: bool = False
    #: Agent: zor görevlerde serbest döngü yerine aşamalı workflow (localize→plan→
    #: patch→verify→review) çalışır. Varsayılan kapalı: mevcut davranış korunur.
    workflow_mode: bool = False
    #: Workflow modunda tur başına sabit model-çağrısı bütçesi (oran sınırı kapısı).
    workflow_max_model_calls: int = 12


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    """Anlamsal arama için gömme sağlayıcısı."""

    #: "local" (ChromaDB gömülü ONNX, çevrimdışı) | "nim" (NVIDIA NIM, çok-dilli)
    provider: str
    #: NIM seçilirse kullanılacak model kimliği.
    model: str


@dataclass(frozen=True, slots=True)
class Config:
    """Uygulamanın tüm yapılandırması. Katmanlara ham dict değil bu nesne geçer."""

    agent: ModelSpec
    #: Fusion havuzu: aynı göreve paralel sorulan modeller.
    candidates: tuple[ModelSpec, ...]
    #: Hakem ve sentez rolü. Hızlı olmalı ve JSON'a sadık kalmalıdır.
    judge: ModelSpec
    #: Görev tipi → tercih edilen aday adı. Bellek katmanı geldiğinde bunu ezecek.
    task_model_map: dict[str, str]
    runtime: RuntimeConfig
    embedding: EmbeddingConfig
    #: Kalıcı belleğin (vektör deposu) tutulduğu dizin.
    memory_dir: Path
    #: Bu yapılandırmanın hangi kullanıcı dosyasından geldiği (yoksa None: yalnız varsayılanlar).
    source: Path | None

    def candidate_by_name(self, name: str) -> ModelSpec | None:
        """Ada göre aday bul; yoksa None."""
        return next((item for item in self.candidates if item.name == name), None)

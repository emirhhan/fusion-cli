"""Tiplenmiş yapılandırma nesneleri.

DİKKAT — bu dosyadaki alanlara varsayılan değer YAZILMAZ. Varsayılanların tek kaynağı
`defaults.yaml`'dır. Eski projede aynı varsayılan hem kodda hem dosyada duruyordu ve
ikisi zamanla ayrıştı (ör. timeout kodda 120, dosyada 45). Alanları zorunlu bırakmak
bu sapmayı derleme/yükleme anında imkânsız kılar: `defaults.yaml` bir alanı unutursa
yapılandırma hiç yüklenmez ve test kırılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core.reasoning import ReasoningEffort
from ..core.types import ModelSpec


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Çalışma zamanı davranışı."""

    request_timeout_s: float
    max_retries: int
    temperature: float
    max_tokens: int
    #: Deterministik olması gereken çağrılar (hakem, sentez, ısıtma) için sıcaklık.
    #: Ana `temperature`'dan ayrıdır: kullanıcı yaratıcılığı artırsa bile hakem
    #: JSON'a sadık kalmalı, seçim kararlı olmalıdır.
    judge_temperature: float
    #: Yardımcı arka plan çağrıları (ders çıkarımı, bağlam sıkıştırma, öz-denetim)
    #: için düşük ama sıfır olmayan sıcaklık.
    utility_temperature: float
    #: Varsayılan reasoning yoğunluğu (mode'dan AYRI). `/effort` ile oturum içinde
    #: değiştirilir. Model desteklemiyorsa sessizce en yakına eşlenir / hiç gönderilmez.
    reasoning_effort: ReasoningEffort
    #: Circuit breaker: bir model arka arkaya kaç kez başarısız olursa devre açılır ve
    #: o model geçici olarak atlanır. Ölü modeli her turda yeniden yoklamamak için.
    circuit_failure_threshold: int
    #: Devre açıldıktan sonra modelin yeniden denenmesi için beklenecek süre (saniye).
    circuit_cooldown_s: float
    #: Güvenilirlik skorunun son-ağırlığı (EWMA). 1'e yakın: son sonuç baskın; 0'a
    #: yakın: geçmiş baskın. Kısa arıza modeli kalıcı kötü saymasın diye orta bir değer.
    reliability_alpha: float
    #: Geçici arızada AYNI modelin yeniden denenmesinden önce beklenecek süreler.
    #: Liste uzunluğu deneme sayısını TANIMLAR: iki gecikme → toplam üç deneme.
    #: Boş liste = yeniden deneme yok. Zincirdeki her modele ayrı ayrı uygulanır.
    retry_delays_s: tuple[float, ...]
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
    #: Hangi sağlayıcıya kilitlenildiği: "auto" | "nvidia" | "openrouter".
    #:
    #: `auto` zinciri iki sağlayıcıya yayar (dayanıklılık). Tek sağlayıcı seçilirse
    #: ötekinin kotasına HİÇ dokunulmaz — bir sağlayıcının tükenmesi ötekini de
    #: tüketmesin diye (ölçüldü: NIM bitince tüm yük OpenRouter'a düştü ve günlük
    #: 50 istek birkaç dakikada bitti).
    provider: str
    #: Sentez, hakemin kararını GÖREREK mi çalışsın?
    #:
    #: False (hızlı kip): hakem ve sentez paralel çalışır, gecikme ikisinin
    #: maksimumudur — ama sentez hangi adayın kazandığını bilmez ve tüm cevapları
    #: eşit ağırlıkta okur; zayıf adayın hatası nihai cevaba sızabilir.
    #: True (doğrulanmış kip): hakem önce çalışır, kararı senteze taşınır. Gecikme
    #: artar; fusion zaten "yavaş ama dikkatli" motordur, hız isteyen agent'ı kullanır.
    verified_synthesis: bool
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
    #: Agent: üretilen HTML/CSS/JS mekanik olarak denetlenir (kırık görsel kaynağı,
    #: boş bağlantı, eksik <main>, stilsiz sınıf oranı, metin/kod tutar çelişkisi).
    #: Varsayılan AÇIK: bulgular modele düzeltme talimatı olarak döner.
    web_verification: bool = True
    #: Agent: üretilen sayfa gerçekten açılıp ölçülür (konsol hatası, yüklenemeyen
    #: kaynak, yatay taşma). `fusion-cli[web]` ekstrası gerekir; kurulu değilse
    #: kapı sessizce geçer.
    browser_verification: bool = True
    #: Agent: üretilen sayfa kırpılıp GÖREN bir modele dar sorular sorulur.
    #: Varsayılan KAPALI: ölçümde ücretsiz görme modelleri açık uçlu kullanımda
    #: güvenilmez çıktı verdi ve her soru ayrı çağrı olduğu için maliyetlidir.
    visual_verification: bool = False
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
class ProfileEligibility:
    """Bir profilin bir modeli ÖNERMESİ için gereken eşikler.

    Eşikler koda gömülmez, `defaults.yaml`'dan gelir (RULES.md "eşikler
    yapılandırmadan okunur"). Filtre yalnızca BİLİNEN-kötü modeli eler; bilinmeyen
    yetenek gizlenmez (gerçekçilik: canlı katalog modellerinin çoğu doğrulanmamıştır).
    """

    #: Gereken en az bağlam penceresi (token). 0 = sınır yok. Model bağlamı
    #: BİLİNİYOR ve bu değerin altındaysa elenir; bilinmiyorsa (0) elenmez.
    min_context: int
    #: `NONE` (araçsız) modele bu profilde izin var mı? Mutation profilleri (medium+)
    #: `false` verir: araçsız model dosya değiştiren agent olamaz (master prompt §5.3).
    allow_no_tools: bool


@dataclass(frozen=True, slots=True)
class TierSpec:
    """Tek bir model kademesi (low, medium, high, ultra, premium).

    Kademe üç rolü BİRLİKTE taşır: kullanıcı tek seçimle motorun tamamını o seviyeye
    alır. Roller ayrı ayrı seçilseydi tutarsız bileşim (küçük agent + büyük hakem)
    sessizce kurulabilirdi; kademe bunu yapısal olarak imkânsız kılar.
    """

    #: Kullanıcının yazdığı kademe adı (`low`, `medium`, …). Küçük harf.
    name: str
    #: Seçim ekranında adın yanında görünen kısa açıklama.
    label: str
    agent: ModelSpec
    judge: ModelSpec
    candidates: tuple[ModelSpec, ...]


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
    #: Görme yetenekli model (görsel doğrulama kapısı). Tanımlı değilse kapı hiç
    #: kurulmaz; görme opsiyoneldir.
    vision: ModelSpec | None = None
    #: Seçilebilir model kademeleri, `defaults.yaml`'daki yazım SIRASIYLA. Sıra
    #: anlamlıdır: seçim ekranı bu sırayı gösterir ve renk geçişini buna yayar.
    tiers: tuple[TierSpec, ...] = ()
    #: Profil adı → uygunluk eşikleri. Model seçim ekranı aktif profile göre bu
    #: eşiklerle süzülür. Tanımsızsa filtre uygulanmaz (özellik sessizce kapanır).
    profile_eligibility: dict[str, ProfileEligibility] = field(default_factory=dict)

    def candidate_by_name(self, name: str) -> ModelSpec | None:
        """Ada göre aday bul; yoksa None."""
        return next((item for item in self.candidates if item.name == name), None)

    def tier_by_name(self, name: str) -> TierSpec | None:
        """Ada göre kademe bul (büyük/küçük harf duyarsız); yoksa None."""
        wanted = name.strip().lower()
        return next((item for item in self.tiers if item.name == wanted), None)

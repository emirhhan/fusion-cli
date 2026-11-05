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
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol, runtime_checkable

from .auto_review import ReviewSource, ReviewVerdict
from .evidence import CriterionEvidence
from .lesson_runtime import LessonDelivery
from .prompt_manifest import PromptManifest
from .repair_ledger import FailureOrigin
from .types import FusionResult, ModelResult

ModelCallPurpose = Literal["actor", "other"]


class Channel(Enum):
    """Metin akışının hangi konuşmaya ait olduğu."""

    MAIN = "main"
    SUBAGENT = "subagent"
    COUNCIL = "council"


@dataclass(frozen=True, slots=True)
class Event:
    """Tüm olayların kökü.

    `agent_id` olayı HANGİ alt ajanın ürettiğini söyler; ana ajanın olaylarında
    boştur. Alt ajanlar paralel koşunca adımları tek kanalda karışır; arayüz her
    ajanın kartını bu alanla ayırır. Alan yalnız anahtar sözcükle verilir ve
    varsayılanı boştur: mevcut olay kurucuları değişmez.
    """

    candidate_id: str | None = field(default=None, kw_only=True)
    agent_id: str = field(default="", kw_only=True)
    event_id: str | None = field(default=None, kw_only=True)
    session_id: str | None = field(default=None, kw_only=True)
    turn_id: str | None = field(default=None, kw_only=True)
    schema_version: int | None = field(default=None, kw_only=True)


@dataclass(frozen=True, slots=True)
class StatusChanged(Event):
    """Kullanıcıya gösterilecek kısa ilerleme bilgisi."""

    message: str


@dataclass(frozen=True, slots=True)
class ModelCallStarted(Event):
    """Bir model çağrısı başlatıldı."""

    call_id: str = field(default="", kw_only=True)

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

    call_id: str = field(default="", kw_only=True)
    requested_model: str = field(default="", kw_only=True)
    #: Çağrının amacı aday adından bağımsızdır; None eski olay kayıtları içindir.
    purpose: ModelCallPurpose | None = field(default=None, kw_only=True)

    role: str
    result: ModelResult
    #: Arka plan işi mi? Bkz. `ModelCallStarted.background`.
    background: bool = False


@dataclass(frozen=True, slots=True)
class ModelCallAbandoned(Event):
    """Başlayan model çağrısı yanıt gelmeden iptal edildi (zaman aşımı, kesilen aday).

    `ModelCallFinished` hiç gelmeyeceği için bu olay olmazsa çağrı muhasebede hiç
    var olmamış sayılırdı. Oysa sağlayıcı isteği almış olabilir: token ve maliyet
    BİLİNMİYOR — sıfır DEĞİL. Dinleyiciler bunu "ölçümü eksik çağrı" diye ayrı
    sayar ve toplamı "alt sınır" olarak gösterir.
    """

    call_id: str = field(default="", kw_only=True)

    role: str
    model: str
    reason: str = "iptal edildi"
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
    """Akıştan metin parçası geldi.

    `provisional` için bkz. `core.types.TextChunk`: nihai cevap değil, araç
    çağrısına eşlik eden öncü beyandır.
    """

    channel: Channel
    text: str
    provisional: bool = False


@dataclass(frozen=True, slots=True)
class TurnAnswered(Event):
    """Turun KABUL EDİLMİŞ nihai cevabı.

    Cevabın ekrana ulaşması eskiden `TokenReceived` yan etkisiydi: model metin
    ürettiği için görünüyordu, motor kabul ettiği için değil. Kapılar bir cevabı
    reddedip modeli tekrar çağırdığında elenen cevap da basılıyor, model kendini
    tekrarladığında aynı metin iki kez düşüyordu.

    Bu olay tur başına EN FAZLA BİR KEZ yayınlanır ve yalnızca motor cevabı kabul
    ettiğinde. Metin zaten akmışsa (gerçekten akıtan API sağlayıcıları)
    yayınlanmaz; iki yol asla aynı anda çalışmaz.
    """

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
class ToolStarted(Event):
    """Bir araç çağrısı BAŞLIYOR (onay gerekiyorsa onaydan SONRA yayınlanır).

    `ToolExecuted` yalnız araç BİTİNCE gelir; araç saniyeler sürerse (büyük bir
    arama, uzun bir kabuk komutu) kullanıcı o süre boyunca hiçbir şey görmez.
    Bu olay, `ToolExecuted`in tersine SESSİZCE kaybolabilir: motor bunu yayınlar
    yayınlamaz aracı çalıştırır, ikinci bir "bitti" olayına gerek duymaz — akışta
    zaten `ToolExecuted` onu izler.
    """

    name: str
    args: Mapping[str, object]
    call_id: str | None = None
    attempt_id: str | None = None


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
    #: `run_shell` için proje kökü parmak izi sonucu: "değişmedi" | "N dosya değişti: ..." |
    #: "ölçülemedi: neden". Boş = ölçüm denenmedi (salt-okunur komut, ayar kapalı).
    workspace: str = ""
    call_id: str | None = None
    attempt_id: str | None = None
    mutating: bool | None = field(default=None, kw_only=True)


@dataclass(frozen=True, slots=True)
class DesktopEscapeStopped(Event):
    """Kullanıcı fiziksel Esc ile masaüstü turunu durdurdu (P-033); arayüz nedenini gösterir."""


@dataclass(frozen=True, slots=True)
class ToolCallRepaired(Event):
    """Model geçersiz bir araç çağrısı yazdı; sözleşme hatırlatılıp yeniden soruldu.

    Onarım SESSİZ kalmamalıdır: her onarım fazladan bir model çağrısı harcar ve
    tekrarlarsa turu bitirir. Ekranda hiçbir iz yokken arka planda üç çağrı yanmış
    olabilir; kullanıcı turun neden uzadığını göremezse Fusion'ı yavaş sanır.
    """

    call_id: str | None = None
    attempt_id: str | None = None
    repair_kind: str = ""
    failure_stage: str = ""


@dataclass(frozen=True, slots=True)
class PreviewReady(Event):
    """Ajan projeyi yerel sunucuda çalıştırdı; kullanıcı bu adresi açabilir.

    Masaüstü uygulaması bu olayla önizleme panelini adresle açar. Ölçüldü (2 Ekim):
    önizleme paneli vardı ama ajan ona hiç adres veremiyordu; kullanıcı "nasıl
    önizlerim" deyince kurulum rehberi okuyordu.
    """

    url: str
    kind: str
    root: str
    title: str = ""


@dataclass(frozen=True, slots=True)
class SubAgentStarted(Event):
    """Bir alt-göreve temiz bağlamlı alt-ajan atandı.

    `agent_id` (kök alan) başlatan ajandır; `sub_id` yeni ajanın kimliğidir ve
    o ajanın bütün olaylarında `agent_id` olarak görünür. Kişilik alanları
    arayüzdeki kartı çizer (ünvan, avatar, renk).
    """

    task: str
    sub_id: str = ""
    persona: str = ""
    title: str = ""
    avatar: str = ""
    color: str = ""
    #: Aynı anda başlatılan kardeş ajan sayısı (paralel grup); tek ajanda 1.
    group_size: int = 1
    started_at: float = 0.0
    #: Yeni ajanın ağaçtaki derinliği (ana ajanın doğrudan çocuğu 1). Üst ajan `agent_id`
    #: alanındadır; arayüz ağacı bu ikisiyle çizer (P-035).
    depth: int = 1


@dataclass(frozen=True, slots=True)
class SubAgentFinished(Event):
    """Alt-ajan işini bitirdi."""

    tool_calls: int
    sub_id: str = ""
    ok: bool = True
    #: Kartta gösterilecek tek satırlık sonuç (ajanın cevabının başı).
    summary: str = ""
    elapsed_s: float = 0.0
    status: str = ""
    changed_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillLoaded(Event):
    """İçerik gerçekten modele yüklendi; uygulanmış iş kanıtı değildir."""

    qualified_name: str
    revision: str
    mode: str = "explicit"
    offset: int = 0
    next_offset: int | None = None
    reference: str = ""


@dataclass(frozen=True, slots=True)
class CouncilConsulted(Event):
    """Zor bir karar için çoklu-model danışması başlatıldı."""

    question: str


@dataclass(frozen=True, slots=True)
class TeacherConsulted(Event):
    """Web öğretmene (`ask_teacher`) danışıldı (Faz 4, Görev 1).

    `council`'dan (çoklu-API-model) AYRI bir olay: öğretmen tek, özel bir web
    oturumudur ve brief'in kırpılıp kırpılmadığı ayrıca izlenmeye değer.
    """

    question: str
    brief_truncated: bool


@dataclass(frozen=True, slots=True)
class TeacherTaskClassified(Event):
    """Kök görevin öğretmen öncesi boyut kararı."""

    size: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TeacherPlanPrepared(Event):
    """Öğretmen planı çırağın görev listesine aktarıldı."""

    steps: int
    structured: bool


@dataclass(frozen=True, slots=True)
class TeacherMemoryUsed(Event):
    """Benzer görevin başarılı planı hafızadan alındı; öğretmene sorulmadı."""

    steps: int
    similarity: float


@dataclass(frozen=True, slots=True)
class TeacherLessonRecorded(Event):
    """Öğretmen planının sonucu ders belleğine işlendi."""

    success: bool
    #: Hafızadan alınan plan mı güncellendi, yoksa yeni plan mı yazıldı.
    reused: bool


@dataclass(frozen=True, slots=True)
class NarrationPublished(Event):
    """Kullanıcıya adımlar arasında yazılan kısa anlatım (giriş ya da adım geçişi)."""

    text: str


@dataclass(frozen=True, slots=True)
class ApprenticeHandoff(Event):
    """Seçili model dosya yazamadığı için iş bu tur çırak modele devredildi."""

    selected_model: str
    apprentice_model: str
    #: Seçili web modeli bu tur öğretmen olarak danışılacak mı?
    teacher_model: str


@dataclass(frozen=True, slots=True)
class PlatformChecked(Event):
    """Dış platforma bağlı istekte resmi kaynak kontrolü yapıldı."""

    platforms: tuple[str, ...]
    #: "resmi-kaynak" (resmi dokümanda arandı) ya da "dogrulanamadi".
    method: str
    sources: int


@dataclass(frozen=True, slots=True)
class TeacherLimitationFound(Event):
    """Doğrulanmamış öğretmen değerlendirmesi ve önerilen alternatif bildirildi."""

    topic: str
    reason: str
    alternative: str


@dataclass(frozen=True, slots=True)
class TierDegraded(Event):
    """Kullanıcının açıkça seçtiği web kademesi gelmedi (Faz 4, Görev 4).

    Yalnız `core.tier.expected_tier(model)` boş DEĞİLKEN (kullanıcı `/auto`
    değil, belirli bir kademe seçtiğinde) yayınlanır. BİLGİLENDİRİR, turu
    ASLA düşürmez (bkz. `web_browser.py:1865` civarındaki geçmiş hata: bir
    kademe-değişim banner'ı turu yanlışlıkla iptal etmişti).
    """

    model: str
    expected_tier: str
    served_by: str


@dataclass(frozen=True, slots=True)
class SelfReviewStarted(Event):
    """Tur sonrası öz-denetim başladı."""


@dataclass(frozen=True, slots=True)
class SelfReviewFinished(Event):
    """Öz-denetim bitti. `completed=False` ise güvenilir hüküm alınamadı."""

    issue_found: bool
    completed: bool = True


@dataclass(frozen=True, slots=True)
class VerificationFailed(Event):
    """Doğrulama kapısı somut ihlal buldu; düzeltici tur çalışacak."""

    summary: str
    findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerificationPassed(Event):
    """Tur sonu kanıt özeti: geçen kontroller ve ölçülemeyenlerin nedeni.

    Geçen kapı eskiden hiçbir olay yaymıyordu (yalnız `VerificationFailed` vardı) ve
    rapor bloğu yalnız `final_text`'e ekleniyordu; cevap akıtılmışsa kullanıcı kapının
    çalıştığını göremiyordu (ölçüldü, 30 Ekim). `checks` GERÇEKTEN çalışıp geçen
    kontrollerdir; `unmeasured` çalışamayan ya da hiç koşmayan kontrollerin nedenidir.
    """

    checks: tuple[str, ...] = ()
    unmeasured: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ChangesDigested(Event):
    """Turda değişen dosyaların GERÇEK fark özeti (modelin anlatımı değil kayıt).

    Satırlar `engines/agent/change_digest.py` tarafından değişiklik kaydından üretilir;
    kullanıcı modelin "şunu düzelttim" iddiasını gerçek farkla karşılaştırabilir.
    """

    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GateEscalated(Event):
    """Kapı iki düzeltmeden sonra da kırmızı; TEK ek tur üst modelle çalışacak.

    Ölçüm izidir: `from_model` düzeltmeleri yapan, `to_model` yükseltilen model;
    `source` üst modelin kaynağı (`ayar` = `runtime.escalation_model`, `kademe` =
    merdiven); `failed_rounds` kapının kaç düzeltmeden sonra hâlâ kırmızı olduğu.
    """

    failed_rounds: int
    from_model: str
    to_model: str
    source: str
    findings: int


@dataclass(frozen=True, slots=True)
class GateEscalationFinished(Event):
    """Üst modelli ek tur bitti ve kapı yeniden ölçüldü.

    `gate_ok` GERÇEK kapı sonucudur (modelin beyanı değil): `True` yeşil, `False`
    kırmızı. `measured=False` ise kapı ölçülemedi (tur bütçesi doldu) ve `gate_ok`
    kırmızı sayılır.
    """

    model: str
    gate_ok: bool
    findings: int
    measured: bool = True


@dataclass(frozen=True, slots=True)
class LessonsRecalled(Event):
    """Göreve benzer dersler bellekten bulundu."""

    count: int
    lesson_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LessonOffered(Event):
    """Kimliği bilinen ders modele gerçekten sunuldu."""

    lesson_id: str
    delivery: LessonDelivery


@dataclass(frozen=True, slots=True)
class LessonOutcome(Event):
    """Ders kullanımının son doğrulanmış veya bilinmeyen sonucu."""

    lesson_id: str
    used: bool | None
    outcome: str
    feedback_reason: str
    evidence_refs: tuple[str, ...] = ()
    failure_origin: FailureOrigin | None = None


@dataclass(frozen=True, slots=True)
class CapabilityActivated(Event):
    """Bir beceri otomatik eşleşti veya kullanıcı tarafından açıkça seçildi."""

    kind: str
    name: str
    source: str
    automatic: bool = True


@dataclass(frozen=True, slots=True)
class LessonsLearned(Event):
    """Turdan yeni ders(ler) çıkarılıp belleğe yazıldı.

    `external`: yazılanlardan kaçı dış içerik (web/tarayıcı/MCP/klonlanan site) okunan
    turdan çıktığı için düşük güvenle "dış kaynaklı" etiketlendi (ölçüm izi).
    """

    count: int
    external: int = 0


@dataclass(frozen=True, slots=True)
class TamperSuspected(Event):
    """Turda ajan var olan bir testi/test komutunu değiştirdi ya da zayıflattı.

    Engelleme değil ölçüm izidir: `count` toplam bulgu, `weakening` bunlardan kanıtı
    düşürenler (skip/assert/test silme, CI değişikliği), `kinds` bulgu türleri
    (`tamper_check.TamperKind` değerleri), `paths` etkilenen yollar (en fazla 10).
    """

    count: int
    weakening: int
    kinds: tuple[str, ...] = ()
    paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextCompressed(Event):
    """Uzun geçmiş özetlenerek kısaltıldı.

    `saved_chars` modelin göreceği görünümde kazanılan karakter (0 = ölçülmedi).
    Mesaj sayısı aynı kalabilir (eski araç çıktıları kısalır); ekranda anlamlı olan
    kazanılan karakterdir.
    """

    before: int
    after: int
    saved_chars: int = 0


@dataclass(frozen=True, slots=True)
class ToolOutputsMasked(Event):
    """Model çağrısına giden görünümde eski araç sonuçları yer tutucuya indirildi.

    Kalıcı geçmiş DEĞİŞMEZ; yalnız modele gönderilen kopya küçülür. Her model
    çağrısında (maskeleme açık ve en az bir sonuç maskeliyse) yayınlanır ki önce/sonra
    karşılaştırılabilsin: `masked` görünümdeki toplam maskeli sonuç, `newly_masked` bu
    çağrıda yeni maskelenenler (önek kayması), `saved_chars` kazanılan karakter,
    `window` ayardaki pencere.
    """

    masked: int
    newly_masked: int
    saved_chars: int
    window: int


@dataclass(frozen=True, slots=True)
class ToolSurfaceOffered(Event):
    """Bir model çağrısına gerçekte sunulan araç yüzeyi (ölçüm izi, yol haritası 4. adım).

    `count` sunulan şema sayısı, `schema_chars` şemaların JSON karakter boyu, `registered`
    kayıt defterindeki SUNULABİLİR (takma ad olmayan) araç sayısı. `compact` sıkı yüzey
    (zayıf model) açık mı, `profile` görev profili (`+` ile birleşik; boş = profil yok),
    `widened` bu turda profil dışı çağrı yüzünden yüzey genişletildi mi.
    """

    count: int
    schema_chars: int
    registered: int
    compact: bool
    profile: str = ""
    widened: bool = False


@dataclass(frozen=True, slots=True)
class RepoMapBuilt(Event):
    """Kök turda depo haritası üretildi (ölçüm izi, yol haritası 8. adım).

    `chars` üretilen metin, `budget_chars` etkin bütçe, `candidates` haritaya uygun dosya,
    `files` gerçekten okunan, `symbols`/`shown` bulunan/gösterilen tanım, `edges` çözülen
    içe aktarma kenarı, `elapsed_ms` süre. `partial` dosya/karakter tavanı ya da zaman
    sınırı yüzünden kısmi (`time_limited` kısmiliğin sebebi zaman sınırı mı), `cached` çözümleme
    önbellekten mi geldi.
    """

    chars: int
    budget_chars: int
    candidates: int
    files: int
    symbols: int
    shown: int
    edges: int
    elapsed_ms: int
    partial: bool = False
    time_limited: bool = False
    cached: bool = False


@dataclass(frozen=True, slots=True)
class NestedInstructionsLoaded(Event):
    """Model alt klasördeki bir dosyaya eriştiği için iç içe talimat dosyaları bağlama eklendi.

    `files` eklenen talimat dosyaları (köke göreli), `chars` eklenen toplam karakter,
    `trigger` tetikleyen dosya yolu.
    """

    files: tuple[str, ...]
    chars: int
    trigger: str


@dataclass(frozen=True, slots=True)
class ToolProfileExpanded(Event):
    """Model profil dışı bir aracı adıyla çağırdı: yüzey bu tur için bir kez genişletildi."""

    tool: str
    profile: str


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
class TurnUsageObserved(Event):
    """Gözlenen tüketim alt sınırı; provider iç retry ölçümü eksik olabilir."""

    prompt_tokens: int
    completion_tokens: int
    unknown_calls: int
    total_calls: int


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
class ExecutionRouteSelected(Event):
    """Kök görev için tek döngü ya da plan motoru seçildi."""

    route: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionPlanCreated(Event):
    """Doğrulanmış tipli plan yürütmeye hazır."""

    plan_id: str
    total_steps: int


@dataclass(frozen=True, slots=True)
class ExecutionStepStarted(Event):
    """Planın tek bir adımı çalışmaya başladı."""

    plan_id: str
    step_id: str
    index: int
    total_steps: int
    goal: str
    #: Bu adımın alt turuna tanınan model çağrısı zarfı; 0 = bilinmiyor.
    #: Adım zarfı politika/tur sınırının ÜSTÜNE çıkabilir (A3-40); arayüz bunu
    #: göstererek maliyet sürprizini önler.
    model_call_limit: int = field(default=0, kw_only=True)


@dataclass(frozen=True, slots=True)
class ExecutionStepVerified(Event):
    """Plan adımının post-condition kanıtı değerlendirildi."""

    plan_id: str
    step_id: str
    ok: bool
    evidence: tuple[str, ...]
    findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionRetryScheduled(Event):
    """Sınıflandırılmış hata için sınırlı kurtarma turu açıldı."""

    step_id: str
    action: str
    attempt: int
    reason: str


@dataclass(frozen=True, slots=True)
class ExecutionCheckpointSaved(Event):
    """Workflow durumu atomik olarak kaydedildi."""

    plan_id: str
    completed_steps: int


@dataclass(frozen=True, slots=True)
class ExecutionPaused(Event):
    """Workflow güvenli biçimde duraklatıldı."""

    plan_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ExecutionCompleted(Event):
    """Plan ve final kabul kapısı başarıyla tamamlandı."""

    plan_id: str
    total_steps: int
    #: İşi kırmayan ama kullanıcının BİLMESİ gereken eksikler — örneğin kabul
    #: kapısının davranışı değil yalnız biçimi kanıtlayabilmiş olması.
    warnings: tuple[str, ...] = ()


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
class FilesChanged(Event):
    """Turda GERÇEKTEN değişen dosyalar.

    Kapanış özeti bugüne kadar modelin hafızasına dayanıyordu ve iki yönde birden
    yanılıyordu: bir koşuda dokunmadığı dosyayı "güncelledim" dedi, başka bir
    koşuda `app/page.tsx`'e doğru düzenlemeyi yaptığı hâlde "hiçbir dosya
    değiştirilmedi" dedi. Liste değişiklik kümesinden gelir; iddia değil kayıttır.
    """

    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NoFileChanges(Event):
    """Tur araç çalıştırdı ama hiçbir dosya/sistem değişikliği yapmadı.

    Ölçüldü (gerçek koşu): model iki dosya OKUDU, hiçbir şey yazmadı ve "entegrasyon
    betiklerini hazırladım, değişen dosyalar: package.json" diyerek turu bitirdi.
    Dosyaların hiçbiri değişmemişti — model okuduğu dosyada zaten var olan bir betiği
    kendi işi gibi raporladı.

    Uydurmayı metinden tanımak dile ve ifadeye bağımlıdır; ama turun sıfır mutasyon
    yaptığı KESİN olarak bilinir. Bu olay o olguyu taşır: yorum değil, sayaç.
    """


@dataclass(frozen=True, slots=True)
class FollowupsSuggested(Event):
    """Turun kanıtından türetilen "sıradaki adım" önerileri.

    Öneriler için YENİ MODEL ÇAĞRISI AÇILMAZ; hepsi `core/followups.py`'de
    turun sayaçlarından üretilir. Kanıt yoksa bu olay HİÇ yayınlanmaz — boş bir
    turun altına öneri basmak gürültüdür.
    """

    #: (etiket, tıklanınca gidecek görev) çiftleri.
    items: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class PlanDrafted(Event):
    """Plan kipindeki tur bitti ve plan dosyaya yazıldı (P-025).

    Arayüz yolu gösterir ("editörde aç"); REPL kabul kartını bunun ardından açar.
    Plan metni olayda TAŞINMAZ: zaten asistan cevabıdır, dosyadan okunur.
    """

    #: Plan dosyasının mutlak yolu.
    path: str
    #: Planın ilk başlığı (yoksa ilk satırı).
    title: str


@dataclass(frozen=True, slots=True)
class TurnOutcome(Event):
    """Runtime'ın kesin tur sonucu; modelin doğal dil iddiasından bağımsızdır.

    `completed`, `partial` ve `failed` değerleri UI tarafından açık bir kapanış
    satırına çevrilir. `TurnFinished` yalnız lifecycle sinyalidir; başarı anlamına
    gelmez ve bu yüzden ayrı tutulur.
    """

    status: str
    elapsed_s: float


@dataclass(frozen=True, slots=True)
class TurnFinished(Event):
    """Tur bitti; dinleyiciler tamponlarını boşaltabilir."""


@dataclass(frozen=True, slots=True)
class AutoReviewDecided(Event):
    """Otomatik kip denetçisi bir çağrıyı sınıflandırdı (P-011).

    `source` modelin mi, kurallı yedeğin mi, önbelleğin mi karar verdiğini söyler;
    sayaçlar karardan SONRAKİ değerlerdir. Denetim günlüğü ve arayüz izi buradan beslenir.
    """

    tool: str
    verdict: ReviewVerdict
    reason: str
    source: ReviewSource
    summary: str
    consecutive: int
    total: int


@dataclass(frozen=True, slots=True)
class AutoModeFellBack(Event):
    """Denetçinin engel eşiği aşıldı; oturum Otomatik'ten Manuel kipe düştü (P-011)."""

    reason: str
    trips: int


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


@dataclass(frozen=True, slots=True)
class PromptManifestRecorded(Event):
    """Gerçek çağrının içeriksiz istem ölçümü; mevcut korelasyonla yayınlanır."""

    manifest: PromptManifest


@dataclass(frozen=True, slots=True)
class ContextProtectionMeasured(Event):
    """Zorunlu son grup ve sınırlı pinler nedeniyle kalan bağlam taşması."""

    threshold_chars: int
    visible_chars: int
    newest_group_chars: int
    pinned_calls: int
    omitted_pins: int
    budget_exceeded: bool


@dataclass(frozen=True, slots=True)
class CandidateStarted(Event):
    """İzole adayın önceden ayrılmış çağrı payı ve istenen modeli."""

    plan_id: str
    step_id: str
    ordinal: int
    requested_model: str
    edit_format: Literal["exact", "whole"] | None
    allocated_calls: int
    arm: str
    task_id: str
    repeat: int


@dataclass(frozen=True, slots=True)
class CandidateFinished(Event):
    """Adayın gerçek çağrı kimlikleri ve seçimden önceki kabul snapshot'ı."""

    plan_id: str
    step_id: str
    ordinal: int
    ok: bool
    criteria: tuple[CriterionEvidence, ...]
    required_criteria: tuple[str, ...]
    call_ids: tuple[str, ...]
    scope: Literal["step", "task"] = field(default="step", kw_only=True)


@dataclass(frozen=True, slots=True)
class CandidateSelected(Event):
    """Seçim uygunluğu başarı değildir; terfi olayı ayrı kaydedilir."""

    plan_id: str
    step_id: str
    selected_candidate_id: str | None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CandidatePromoted(Event):
    """Asıl çalışma alanında terfi sonrası yeniden ölçülen kabul snapshot'ı."""

    plan_id: str
    step_id: str
    ok: bool
    criteria: tuple[CriterionEvidence, ...]
    required_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceConflictDetected(Event):
    """Kaynak terfisi ve geri alma çakışmalarını metin ayrıştırmadan say."""

    plan_id: str
    step_id: str
    phase: Literal["source-promotion", "rollback"]
    count: int


@dataclass(frozen=True, slots=True)
class AttemptExperimentFinished(Event):
    """Bütün adımlar ve final kabulünden sonra aynı toplam hakla biten kol."""

    task_id: str
    repeat: int
    arm: str
    ok: bool
    criteria: tuple[CriterionEvidence, ...]
    required_criteria: tuple[str, ...]
    used_calls: int
    total_calls: int
    measurement: Literal["measured", "unavailable"] = field(default="measured", kw_only=True)


@dataclass(frozen=True, slots=True)
class TeacherAdviceOffered(Event):
    """Cevabı saklamadan öğretmen tavsiyesini mevcut tur kimliğine bağla."""

    advice_id: str


@dataclass(frozen=True, slots=True)
class TeacherAdviceOutcome(Event):
    """Tavsiyenin ilgili son kanıtla doğrulanma durumu."""

    advice_id: str
    verified: bool
    evidence_refs: tuple[str, ...] = ()

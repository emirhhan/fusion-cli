"""Tiplenmiş yapılandırma nesneleri.

DİKKAT — bu dosyadaki alanlara varsayılan değer YAZILMAZ. Varsayılanların tek kaynağı
`defaults.yaml`'dır. Eski projede aynı varsayılan hem kodda hem dosyada duruyordu ve
ikisi zamanla ayrıştı (ör. timeout kodda 120, dosyada 45). Alanları zorunlu bırakmak
bu sapmayı derleme/yükleme anında imkânsız kılar: `defaults.yaml` bir alanı unutursa
yapılandırma hiç yüklenmez ve test kırılır.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ..core.auto_review import AutoClassifierMode
from ..core.desktop_settings import DesktopSettings
from ..core.execution_mode import ExecutionMode
from ..core.reasoning import ReasoningEffort
from ..core.routing_strategy import RoutingStrategy
from ..core.types import ModelSpec
from ..core.window_mode import WindowMode
from .sandbox_config import SandboxConfig


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
    #: Yedek zincirinin deneme sırası stratejisi. `priority` mevcut ölçülmüş sırayı
    #: korur; diğerleri (free_first, headroom, least_used, round_robin, random) yalnızca
    #: kullanıcı açıkça seçerse devreye girer (gateway'de). Bkz. core/routing_strategy.
    routing_strategy: RoutingStrategy
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
    #: Agent modunda model çağrısı üst sınırı; `None` = sınır yok. Varsayılan 400
    #: (güvenlik tavanı, Z1-40; bkz. `defaults.yaml`).
    #: Turun TAMAMI için geçerlidir: öz-denetim ve doğrulama kapısının açtığı
    #: düzeltici turlar da aynı bütçeden yer.
    agent_max_steps: int | None
    #: Ardışık kaç araç turu hiçbir ilerleme (başarılı araç / dosya dokunuşu)
    #: üretmezse modele "sıradaki somut adımı at" notu gönderilir. Tur kesilmez.
    agent_max_idle_rounds: int
    #: Agent: tur bitince denetçi model sonucu kontrol eder, gerekirse düzeltir.
    self_review: bool
    #: Agent: araç hatasında modele "farklı yaklaş" notu enjekte edilir.
    reflexion: bool
    #: Agent: her görevden ders çıkarılır ve benzer görevlerde promptta hatırlatılır.
    lessons: bool
    #: Karmaşık bir değişiklik görevinde öğretmen yanıtı alınmışken toplam araç
    #: çağrısı bu sınıra ulaşıp dosya hâlâ değişmemişse web öğretmeni devralır.
    #: 0 devralmayı kapatır; açıkça seçilen zorunlu model hiçbir zaman değişmez.
    agent_teacher_takeover_tools: int = 10
    #: `ask_teacher` aracı modele HİÇ SUNULMAZ — `config.teacher` tanımlı olsa
    #: bile. Kullanıcının "öğretmensiz çalış" tercihi (Faz 4, Görev 3); `council`
    #: bundan ETKİLENMEZ, o ayrı ve çoklu-API-model bir araçtır.
    teacherless: bool = False
    #: `ask_teacher`'ın öğretmen cevabından çıkardığı ders `ChromaLessonMemory`'ye
    #: de yazılsın mı (model `recall_lessons` ile geri çağırabilsin)? Varsayılan
    #: AÇIK. Çakışan bir ders bulunursa (bkz. `engine_tools._ogretmen_dersi_yaz`)
    #: yazılmaz ve kullanıcıya bunu kapatma seçeneği sunulur — açıp kapamak bu
    #: bayrakla olur, `.fusion/ogretmen.md` günlüğü bundan ETKİLENMEZ, o her
    #: zaman yazılır.
    teacher_lesson_sync: bool = True
    #: Web sohbet oturumları yanıt vermezse öğretmen için Codex (ChatGPT'nin KODLAMA
    #: limiti) son yedek olarak denensin mi? Varsayılan KAPALI: öğretmen yalnız
    #: ChatGPT/Gemini SOHBET limitlerini harcar; Codex limiti ancak kullanıcı isterse.
    teacher_codex_fallback: bool = False
    #: Birincil model (yerel/API) cevap veremezse, girişi doğrulanmış ve araç ölçümünü
    #: geçmiş web oturumlarına otomatik geç (bağlam taşması, model kapalı, sunucu hatası).
    auto_web_fallback: bool = False
    #: Modele HİÇ SUNULMAYACAK araçların adları (takma adları da kapanır). Kullanıcı bir
    #: aracı istemiyorsa ya da bir yeteneği araçsız ölçmek istiyorsa (ör. `clone_site`
    #: kapalıyken model siteyi kendisi kurabiliyor mu?) buradan kapatır.
    disabled_tools: tuple[str, ...] = ()
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
    #: Arayüz teması: "system" | "light" | "dark".
    #
    # Neden YAPILANDIRMADA — ölçüldü (11 Eylül): tercih webview `localStorage`'ında
    # tutuluyordu ve o depo kullanıcının kurulumunda hiç yazılmıyordu
    # (`WebsiteData/LocalStorage` 0 bayt). Yazma hatası yutulduğu için tercih her
    # açılışta `system`'e düşüyor, macOS koyu temadayken içerik beyaz kalıyor ve
    # kullanıcı koyuyu seçse bile sonraki açılışta unutuluyordu. Yapılandırma
    # katmanı zaten kalıcı ve sınanmış; tercih oraya taşınır.
    theme: str = "system"
    #: Zeka motoru: "agent" | "fusion". Eskiden yalnız oturumda yaşıyor, uygulama
    #: yeniden açılınca tek ajana dönüyordu; artık kullanıcının seçimi kalıcıdır.
    engine: str = "agent"
    #: İzin modu: "auto" | "edits" | "security" | "plan". `bypass` BİLEREK kalıcı
    #: değildir (tek tuşla yanlışlıkla açılmamalı); yalnız oturum boyunca geçerlidir.
    approval_mode: str = "auto"
    #: Agent: istek bir playbook'u tetiklerse serbest döngü yerine deterministik akış
    #: çalışır (daha az model çağrısı). Varsayılan kapalı: mevcut davranış korunur.
    playbooks: bool = False
    #: Agent: varsayılan tek döngüdür (`OFF`); `ALWAYS` her kök turu plan
    #: motoruna sokar. Eski `auto` ve boolean değerler bkz. `ExecutionMode._missing_`.
    workflow_mode: ExecutionMode = ExecutionMode.OFF
    #: Workflow modunda tur başına sabit model-çağrısı bütçesi (oran sınırı kapısı).
    workflow_max_model_calls: int = 12
    #: Tipli plan üretimi ve onarım çağrıları için zarf.
    #
    # 2 iken tek onarım hakkı vardı ve iki farklı onarım sebebi onun için
    # yarışıyordu: bozuk JSON (biçim) ve eksik teslimat (kapsama). Ölçüldü
    # (13 Eylül, Godot koşusu): plan asset/UI/ara sahne adımı içermedi, kapsama
    # onarımı için hak kalmadı ve koşu iskeletle "tamamlandı" dedi. 3 ile her iki
    # onarım aynı planlama evresinde yapılabilir.
    workflow_planning_calls: int = 3
    #: Plan kipinde biten turun planı `plans/<sohbet>.md` dosyasına yazılır ve
    #: `PlanDrafted` yayınlanır (P-025). Kapalıyken plan yalnız sohbette kalır.
    plan_files: bool = True
    #: Her plan adımının bağımsız model çağrısı zarfı.
    #
    # Bir adım TEK bir alt-tur olarak çalışır ve o alt-tur kendi tur sınırına
    # kadar (web/karmaşık: 28) model çağrısı harcayabilir. Zarf bundan küçükse
    # fatura ilk adımda kesilir. Ölçüldü (Godot koşusu): 8 ile, 20 başarılı
    # araç çağrısıyla ilerleyen adım hiç tamamlanamadan duraklatıldı.
    workflow_step_calls: int = 24
    #: Bir plan adımının hata sınıflandırmasından sonra kullanabileceği kurtarma çağrısı.
    #
    # Kurtarma da bir alt-turdur; iki çağrılık zarf ilk denemede taşıyordu.
    # Kör tekrarı bu sayaç değil hata sınıflandırması ve `retry_safety` engeller.
    #
    # Adım zarfı gerçek işin boyuna açıldığında (bkz. `execution_policy`) kurtarma
    # da onunla orantılı olmalı: düşen bir adımı 12 çağrıyla toparlamak, adımın
    # kendisi 90 çağrı harcayabiliyorken anlamsız bir darlıktı.
    workflow_recovery_calls: int = 24
    #: Final kabul doğrulaması ve gerekirse raporlama çağrısı zarfı.
    workflow_final_verification_calls: int = 2
    #: Paralel deneme (test-time scaling) için EK çağrı hakkı.
    #
    # Varsayılan 0: özellik opt-in'dir ve yapılandırılmadan tek fazla çağrı
    # harcanmaz. Açıldığında adım izole kopyalarda birkaç kez koşar ve kazanan
    # kanıtla seçilir; maliyet artar, kazanç ölçülür.
    workflow_attempt_calls: int = 0
    #: Gateway: aynı istek (model+mesajlar) tekrar gelirse önbellekten anında dön (token
    #: tasarrufu). Yalnızca gateway'i etkiler; agent/fusion motorları etkilenmez.
    gateway_cache: bool = True
    #: Gateway: giden mesajlarda güvenli sıkıştırma (fazla boş satır + satır sonu boşluğu).
    #: İçerik BOZULMAZ; kod girintisi korunur. Varsayılan kapalı (opt-in).
    gateway_compression: bool = False
    #: Gateway: yanıtta sızan sır/anahtar deseni maskelenir (credential guardrail).
    gateway_mask_secrets: bool = True
    #: Web AI alışverişini diske yaz (teşhis). Varsayılan kapalı: gönderilen prompt
    #: dosya içeriği taşır ve onu diske yazmak gizlilik genişletmesidir.
    web_trace: bool = False
    #: Dosya araçları yalnızca proje kökü (+ `--add-dir`) altında mı çalışsın?
    #: Varsayılan KAPALI: kullanıcı kök dışındaki projelerde/dosyalarda da çalışabilsin.
    #: `true` yapıldığında kök dışına erişim `PathAccessError` ile reddedilir.
    restrict_to_root: bool = False
    #: Tek yönlü kök sınırı (P-002, Claude `permissions.blockReadsOutsideWorkingDirectories`
    #: / `blockWritesOutsideWorkingDirectories`): açıkken dosya araçları kök (+ `--add-dir`)
    #: dışını OKUYAMAZ / dışına YAZAMAZ ve onay bile sorulmaz. Varsayılan kapalı.
    block_reads_outside_root: bool = False
    block_writes_outside_root: bool = False
    #: Agent turunda geçici model hatasında (429, 5xx, zaman aşımı) yeniden deneme
    #: sayısı; beklemeler üstel artar. 0 = yeniden deneme yok. Varsayılan 4: 429'da
    #: yedeğe beklemeden geçilir (bkz. `loop.MAX_TRANSIENT_RETRIES`, Z1-35).
    model_retry_attempts: int = 4
    #: Sağlayıcı kimliği → MODEL başına dakikalık istek sınırı. Bilinen sınır önden
    #: korunur (paralel ajanlar ve sekmeler ortak kovadan hak alır) ki 429 hiç
    #: gelmesin. Listede olmayan sağlayıcı yavaşlatılmaz; yalnız 429'u paylaşılır.
    rate_limit_per_minute: dict[str, float] = field(default_factory=dict)
    #: Kovadan hak için en fazla bu kadar beklenir; daha uzunsa çağrı yapılmadan
    #: zincirdeki yedeğe geçilir.
    rate_pace_max_wait_s: float = 3.0
    #: `spawn_agents` ile aynı anda koşabilecek alt ajan sayısı. Asıl hız sınırını
    #: paylaşılan defter korur; bu tavan bağlamı ve kullanıcının takip edebileceği
    #: kart sayısını sınırlar. 8: Claude Code 20, dynamic workflows 16 eşzamanlı
    #: çalıştırır; ücretsiz model kotası paylaşılan kova ile korunduğundan 4'ün yarım
    #: bıraktığı paralel araştırma+kodlama dalgaları için ikiye katlandı (P-035).
    max_parallel_agents: int = 8
    #: Alt ajanın alt ajan başlatabileceği en büyük derinlik: 1 = yalnız ana ajan
    #: başlatır (eski davranış), 2 = alt ajan bir kat daha açabilir, 3 = Claude Code'un
    #: sınırı. Her derinlik bağlamı ve adım bütçesini yarılar (bkz. `team.child_step_limit`).
    max_agent_depth: int = 2
    #: Bir kök turda (tüm derinlikler toplam) başlatılabilecek alt ajan sayısı; dolunca
    #: `spawn_agent` "bütçe doldu" döner. Sonsuz ajan ağacı kotayı tüketmesin.
    max_subagents_per_turn: int = 20
    #: Turdan bağımsız arka plan ajan görevleri (P-048): `/bg`, Ctrl+B, `fusion agent --bg`,
    #: `spawn_agent(arka_plan=true)`. False = hiçbir yüzey arka plan görevi başlatmaz.
    background_agents: bool = True
    #: Aynı anda etkin (sırada/çalışıyor/girdi bekliyor) arka plan görevi tavanı.
    max_background_agents: int = 4
    #: Arka plan görevinin onay/soru cevabı için bekleme (saniye); dolunca "sorulamadı".
    background_input_timeout_s: float = 1800.0
    #: Bitmiş arka plan görevlerinin saklanma süresi (gün); yeni görev başlarken daha eskileri
    #: silinir. 0 = hiç silme.
    background_retention_days: int = 14
    #: Oturumlar arası mesajlaşma (P-060): oturum defterine kayıt, list_agents/send_message.
    cross_session_messaging: bool = True
    #: Başka oturumdan gelen mesaj: accept (boşta tur olur) | hold (bekletilir; varsayılan)
    #: | refuse (reddedilir). Claude Code `crossSessionInbound` karşılığı.
    cross_session_inbound: str = "hold"
    #: Dinamik iş akışları (P-062, `workflow_run`, `/workflows`): model JSON tanımıyla çok
    #: sayıda alt ajanı paralel/boru hattı olarak yönetir. False = araç sunulmaz.
    dynamic_workflows: bool = True
    #: Bir iş akışı koşusunun başlatabileceği en fazla alt ajan (Claude Code 1.000/koşu;
    #: Fusion'da ücretsiz kota ortak kovadan yandığı için 50). Tanım yalnız daraltır.
    dynamic_workflow_max_agents: int = 50
    #: İş akışında aynı anda koşan ajan tavanı; 0 = `max_parallel_agents`.
    dynamic_workflow_max_concurrent: int = 0
    #: Bu kadar ya da daha çok ajan başlatacak koşu önce kullanıcıya sorulur; 0 = sorma.
    dynamic_workflow_confirm_agents: int = 10
    #: Ajan ekipleri (P-061, `team_run`, `/team`): lider + eşzamanlı üyeler, paylaşımlı
    #: görev listesi ve posta kutusu (`.fusion/ekip/<ad>/`). False = araç sunulmaz.
    agent_teams: bool = True
    #: Bir ekibin en fazla üyesi (Claude Code önerisi 3-5).
    agent_team_max_members: int = 5
    #: Koşusu biten üyenin iş/mesaj gelince en fazla kaç kez yeniden uyandırılacağı.
    agent_team_max_wakes: int = 3
    #: Tek `team_run` çağrısındaki toplam üye koşusu (uyanmalar dahil) tavanı.
    agent_team_max_runs: int = 16
    #: Yeni ekip kurulmadan önce maliyet uyarısıyla sorulsun mu (ekip ~7 kat token).
    agent_team_confirm: bool = True
    #: Ajan bir dosyayı değiştirince o dosya için çalışacak kullanıcı komutları
    #: (`{path}` yerine dosya yolu). Boş = kanca yok (varsayılan davranış).
    post_edit_commands: tuple[str, ...] = ()
    #: Genel kanca sistemi (P-009, `config/hooks.py`): false = hiçbir kanca çalışmaz.
    hooks_enabled: bool = True
    #: `~/.claude/settings.json` kancaları da çalışsın mı? Varsayılan kapalı: oradaki Claude
    #: betikleri (ECC vb.) Fusion'ın her araç çağrısında çalışır. Proje `.claude/` dosyaları
    #: bu anahtardan bağımsızdır (`fusion trust` ister).
    claude_hooks: bool = False
    #: Süresi yazılmamış kancanın en uzun çalışma süresi (sn); tek kanca en çok 600 sn.
    hook_timeout_s: float = 60.0
    #: Öğretmenle (web sohbet) tek bir soru-cevap için en fazla bekleme. Genel API
    #: zaman aşımından (`request_timeout_s`) AYRIDIR: web LLM düşünme süresi uzun
    #: olabilir ama bir tur dakikalarca öğretmeni bekleyemez (A4-31).
    teacher_timeout_s: float = 300.0
    #: `run_shell` işletim sistemi sandbox'ı: "off" (varsayılan) | "write_root" (macOS
    #: `sandbox-exec`, Linux bubblewrap; Q1-16). Neyin sınırlandığı `sandbox:` bölümünde (P-010).
    shell_sandbox: str = "off"
    #: Küçük/zayıf model için SIKI araç yüzeyi eşiği (T1-63): bilinen girdi penceresi
    #: (token) bu değere eşit ya da küçükse model masaüstü (`desktop_*`) ve Chrome
    #: (`chrome_*`) araçlarını, istek masaüstü işi değilse, hiç görmez. 41+ şemanın
    #: tamamı küçük bağlamda hem araç seçimini bozar hem bağlamı yer. 0 = pencereye
    #: bakma (yalnız `compact` etiketi ve doğrulanmamış taklit araç modeli sıkı yüzey alır).
    compact_tools_window_tokens: int = 32768
    #: Sıkı yüzeyli modele sunulacak EN FAZLA MCP/eklenti aracı sayısı (M1-12); registry
    #: sırasıyla ilk N. 0 = sınır yok.
    compact_external_tools: int = 12
    #: Sıkı yüzeyli (zayıf) modele görev türüne göre SABİT araç alt kümesi (yol haritası
    #: 4. adım): soru/okuma, kod düzenleme, web, oyun/medya, masaüstü. Tür, konuşmanın
    #: istekleriyle belirlenir ve yalnız genişler. False = bugünkü sıkı yüzey. Güçlü modele
    #: etkisi yoktur.
    weak_model_tool_profiles: bool = True
    #: Kayan pencere maskeleme: modele giden görünümde yalnız son N araç sonucu (ve son
    #: assistant mesajından sonraki TÜM paralel sonuçlar) tam kalır; daha eskileri kısa
    #: bir yer tutucuya iner (araç adı, argüman özeti, durum, varsa artifact yolu).
    #: Kalıcı geçmişe dokunulmaz, eşik beklenmez. 0 = kapalı. 8: SWE-agent son ~5
    #: gözlemi, JetBrains (arXiv 2508.21433) 10 gözlemlik pencereyi iyi buldu; paralel
    #: çağrılar ve toplu kayma payı (N/2) ayrıca tam kaldığından 8 ikisinin ortasıdır.
    tool_output_window: int = 8
    #: Zayıf/küçük model (`compact` etiketi ya da pencere <= `compact_tools_window_tokens`)
    #: Fusion'ın kendi yazdığı düz metin otomatik bellek (P-036): `BELLEK.md` indeksinin ilk
    #: 200 satırı her turun bağlamına girer, `remember`/`memory_read` araçları sunulur, REPL'de
    #: `#` notu buraya yazar. False = araçlar sunulmaz, blok eklenmez (Claude `autoMemoryEnabled`).
    auto_memory: bool = True
    #: Bellek dizini; boş = `<bellek>/projeler/<proje>/bellek` (Claude `autoMemoryDirectory`).
    auto_memory_dir: str = ""
    #: için sıkıştırma eşiği, pencerenin bu oranı kadar karakterdir (token x 3). 0 = kapalı
    #: (eşik yalnız genel formülden gelir). 0.2: TAHMİN, canlı ölçümle güncellenecek;
    #: küçük modeller nominal pencerenin ancak bir kısmında güvenilir kalır (context rot).
    weak_model_compaction_ratio: float = 0.2
    #: `edit_file`/`multi_edit` tam eşleşme bulamayınca satır sonu boşluğu, girinti
    #: (sekme/boşluk, ortak kayma) ve CRLF farkını tolere eden yedek yolu dener; YALNIZ tek
    #: ve belirsiz olmayan blokta uygular, sonuç modele açıkça bildirilir. Varsayılan AÇIK:
    #: Aider'ın düzenleme ölçümünde esnek eşleşme boşluk/girinti kaynaklı düzenleme
    #: hatalarını ~9 kat azalttı; yanlış eşleşme riski tek-eşleşme şartıyla sınırlı.
    edit_fuzzy_match: bool = True
    #: Dosya yazıldıktan sonra (edit_file/multi_edit/write_file) JS/TS/PHP için hızlı
    #: sözdizimi kontrolü; hata varsa dosya yine yazılır, sonuca "sözdizimi hatası: satır N"
    #: eklenir. Denetleyici yoksa sessizce atlanır. Python zaten yazmadan önce engellenir.
    post_edit_syntax_check: bool = True
    #: `run_shell` öncesi ve sonrası proje kökünün hafif parmak izi (boyut + mtime) alınır:
    #: komut dosya DEĞİŞTİRMEDİYSE mutasyon sayılmaz, önceki testin kanıtı bayatlamaz.
    #: Ölçüldü (30 Ekim): tanınmayan `python3 -m paket.cli listele` temkinli olarak mutasyon
    #: sayılıp geçen testi eskitiyordu. Proje kökü DIŞINA yazan komut görünmez; sınır
    #: aşılır (20.000 dosya / 300 ms), komut arka plandaysa ya da kapalıysa eski temkinli davranış.
    shell_workspace_fingerprint: bool = True
    #: `desktop_screenshot` modele gitmeden bu genişliğe (piksel) küçültülür; koordinat çerçevesi
    #: sonuçta bildirilir ve fare araçları görüntü pikselini ekran noktasına çevirir (P-030).
    #: 1568: vision modellerinin kayıpsız kenarı; Claude computer-use ~1372'ye indirir.
    desktop_screenshot_max_width: int = 1568
    #: `desktop_screenshot` Fusion'ın kendi penceresini (ve CLI'de terminali) görüntüden çıkarır
    #: (ScreenCaptureKit, macOS 14+); model kendi sohbetini görmez. Kapalıysa ya da yardımcı
    #: yoksa `screencapture` ile tam ekran alınır (P-033).
    desktop_exclude_fusion_window: bool = True
    #: Doğrulama kapısı iki düzeltme turundan sonra HÂLÂ kırmızıysa, kullanıcının
    #: yapılandırmasında tanımlı BİR üst model varsa TEK bir ek düzeltme turu o modelle
    #: koşar (bkz. `engines/agent/gate_escalation.py`). Sinyal yalnız gerçek kapı
    #: sonucudur. Üst model tanımlı değilse (ya da seçilen model `strict` ise) hiçbir
    #: şey yapılmaz. Varsayılan AÇIK: ek tur yalnız zaten başarısız bir turda ve en çok
    #: bir kez koşar; ücretli sağlayıcı çağırmaz, hız sınırı kapısından geçer.
    escalate_on_gate_failure: bool = True
    #: Yükseltmede kullanılacak model (`<sağlayıcı>/<model>`). Boş = kademe merdiveninden
    #: otomatik seç: seçili modelin kendi yedek zincirinde bulunan, merdivende ondan
    #: sonra gelen kademenin baş modeli. Doluysa kullanıcının açık tanımıdır; yine de
    #: araç yetenekli olmalı ve web/Codex oturumu olmamalıdır.
    escalation_model: str = ""
    #: Tur sonunda ajanın test/CI dosyalarına dokunuşu denetlenir (`tamper_check.py`): var olan
    #: testte skip/xfail/.only eklenmesi, assert ya da test silinmesi, test dosyasının silinmesi,
    #: CI iş akışı / pytest yapılandırması / `test` betiği değişikliği "şüpheli" işaretlenir ve
    #: "testler geçti" kanıtı tek başına başarı sayılmaz. ENGELLEMEZ, yalnız işaretler ve uyarır.
    #: Varsayılan AÇIK: ImpossibleBench ajanların geçemediği testi değiştirerek "başarı"
    #: gösterdiğini ölçtü; denetim dosya içeriğini bir kez okur, maliyeti ihmal edilebilir.
    test_tamper_check: bool = True
    #: Ders çıkarılan turda dış içerik (web/tarayıcı/MCP/klonlanan site) okunduysa çıkan dersin
    #: başlangıç güveni (0..1) ve "doğrulanmamış dış kaynaklı" etiketi. Güven eşiği
    #: (`LESSON_CONFIDENCE_FLOOR` 0.35) üstünde kalmalı ki ders geri çağrılıp sınanabilsin; ama
    #: normal derse (1.0) göre düşüktür ve dış içerik okunan başarılı turda artmaz: yalnız
    #: dış içeriksiz başarılı bir tur dersi doğrular. 0.5: tek başarısız tur (-0.20 → 0.30)
    #: dersi eşiğin altına indirir; yani zehirli bir ders ilk başarısızlıkta devre dışı kalır
    #: (MINJA bellek zehirlemesine karşı ucuz bir hız sınırı). TAHMİN: canlı ölçümle güncellenecek.
    external_lesson_confidence: float = 0.5
    #: Kök turda sistem bağlamına giren depo haritasının bütçesi (karakter; ~3 karakter/token).
    #: 0 = harita kapalı. 3000 ≈ 1k token: Aider'ın repo-map bütçesiyle aynı ölçek; eski 1500
    #: değeri bu deponun haritasında yalnız ~10 dosyaya yetiyordu. Küçük pencereli modelde
    #: harita pencerenin %3'ünü aşmaz (bkz. `engines/agent/repo_context.effective_budget`).
    repo_map_chars: int = 3000
    #: Model alt klasördeki bir dosyayı okuyup/düzenlediğinde o klasör ve üst klasörlerindeki
    #: (kök hariç) AGENTS.md/CLAUDE.md bir kez, kısa biçimde bağlama eklenir (Claude Code'un
    #: iç içe CLAUDE.md davranışı). Proje kökü dışına çıkılmaz; içerik güvenilmez girdi
    #: olarak etiketlenir. False = yalnız kök talimatı.
    nested_instructions: bool = True
    #: Çıktı stili (P-068): `varsayilan` | `ozlu` | `aciklayici` | `ogretici` ya da
    #: `~/.fusion/cikti-stilleri/<ad>.md` / `.claude/output-styles/<ad>.md` dosyasının adı.
    #: Stil metni sistem istemine kodlama talimatlarından SONRA eklenir; `varsayilan` hiçbir
    #: şey eklemez. `/output-style` ile değişir.
    output_style: str = "varsayilan"
    #: Durum satırı betiği (P-069): boş = yerleşik durum çubuğu. Doluysa her tur sonunda
    #: komut stdin'den JSON (model, workspace, cost, context_window, session…) alıp tek
    #: satır basar; 1 sn zaman aşımı, hata olursa yerleşik satıra dönülür. `/statusline`.
    status_line_command: str = ""
    #: Terminal renk teması (P-070): `koyu` | `acik` | `ansi` | `daltonizm`. Masaüstü
    #: temasından (`theme`) AYRIDIR. `/theme` ile değişir ve kalıcılaşır.
    terminal_theme: str = "koyu"
    #: REPL görünümü (P-070): `fullscreen` (varsayılan, Ink-benzeri tam ekran) | `inline`
    #: (eski satır-içi yol; FUSION_INLINE=1 ile aynı). `/tui` ile değişir, yeni oturumda uygulanır.
    tui: str = "fullscreen"
    #: Vim düzenleme kipi (P-067): girdi satırı NORMAL/INSERT kiplerinde çalışır. `/vim`.
    vim_mode: bool = False
    #: Talimat katmanları birleştirilsin mi: `~/.claude/CLAUDE.md` + `~/.codex/AGENTS.md`
    #: (kullanıcı), `CLAUDE.md` + `.claude/CLAUDE.md` + `CLAUDE.local.md` (proje), `@yol`
    #: içe aktarmaları ve `.claude/rules` kuralları. False = eski davranış: yalnız kökteki
    #: ilk bilinen dosya.
    instruction_merge: bool = True
    #: Bütün talimat katmanlarının toplam bütçesi (karakter). Aşılırsa kırpma metne not düşer.
    instruction_max_chars: int = 32_000
    #: Kök turda sistem bağlamına giren beceri dizininin bütçesi (karakter): beceri başına
    #: `ad — açıklama` satırı; model uygun beceriyi aramadan tanır (Claude Code'un progressive
    #: disclosure davranışı). 0 = dizin kapalı (yalnız find_skill). Küçük pencereli modelde
    #: pencerenin %2'sini aşmaz.
    skill_index_chars: int = 4_000
    #: Proje talimatı ve dış araç bellekleri tur başında okunsun mu? `fusion agent --bare`
    #: kapatır (Claude Code `--bare`); varsayılan açık (P-026).
    project_instructions: bool = True
    #: Agent turunun BİLİNEN maliyeti (USD) için tavan; `None` = tavan yok. Dolunca tur
    #: `BudgetStop.COST_LIMIT` ile kapanır (`fusion agent --max-budget-usd`; P-026).
    agent_max_cost_usd: float | None = None
    #: Model çağrısı/MCP/beceri kullanımını `memory_dir/usage.jsonl`'e yaz (`/usage` pencereleri,
    #: `fusion insights`). İstem metni yazılmaz. False = yalnız oturum sayacı (P-056).
    usage_log: bool = True
    #: Otomatik kip denetçisi (P-011): `off` | `ask_only` | `on` (bkz. `core.auto_review`).
    #: Sorulacak çağrıyı küçük/hızlı rol modeli sınıflandırır; güvenliyse sorulmaz. Varsayılan
    #: kapalı: açılınca kullanıcı mesajları hakem sağlayıcısına gider (açık seçimle açılır).
    auto_classifier: AutoClassifierMode = AutoClassifierMode.OFF
    #: Denetçi modeli: boş = hakem (`judge`) rolü ve yedekleri; dolu = `<sağlayıcı>/<model>`.
    auto_classifier_model: str = ""
    #: Tek sınıflandırma çağrısının süre sınırı (saniye). Aşılırsa kurallar geçerli olur.
    auto_classifier_timeout_s: float = 12.0


class SkillVisibility(StrEnum):
    """Becerinin görünürlüğü (Claude Code `skillOverrides`; P-051). Türkçe adlar da kabul edilir."""

    #: Olağan: dizinde ad + açıklama, model ve kullanıcı çağırabilir.
    ON = "on"
    #: Dizinde yalnız ad (açıklama bağlam harcamaz); çağrı serbest.
    NAME_ONLY = "name-only"
    #: Yalnız kullanıcı `/ad` ile çağırır; model dizinde görmez, kendiliğinden yüklemez.
    USER_INVOCABLE_ONLY = "user-invocable-only"
    #: Hiç sunulmaz (kalıcı kapatma ile aynı).
    OFF = "off"

    @classmethod
    def _missing_(cls, value: object) -> SkillVisibility | None:
        # YAML 1.1 tırnaksız `off`/`on` yazımını boolean okur (ölçüldü 31 Ekim: `x: off`
        # "geçersiz değer False" veriyordu); kullanıcının kastettiği açıktır.
        if isinstance(value, bool):
            return cls.ON if value else cls.OFF
        aliases = {
            "acik": cls.ON,
            "açık": cls.ON,
            "yalniz-ad": cls.NAME_ONLY,
            "yalnız-ad": cls.NAME_ONLY,
            "yalniz-kullanici": cls.USER_INVOCABLE_ONLY,
            "yalnız-kullanıcı": cls.USER_INVOCABLE_ONLY,
            "kapali": cls.OFF,
            "kapalı": cls.OFF,
        }
        return aliases.get(str(value).strip().lower())


@dataclass(frozen=True, slots=True)
class CapabilitiesConfig:
    """Beceri/ajan kataloğu tercihleri (P-051)."""

    #: Kalıcı olarak kapatılan beceri/ajan adları (düz ad ya da `ad@kaynak:kimlik`). Masaüstü
    #: kataloğundaki oturumluk kapatmadan farklı: her oturumda uygulanır.
    disabled: tuple[str, ...] = ()
    #: Beceri adı (ya da `ad@kaynak:kimlik`) → görünürlük; listede olmayan beceri `on`.
    overrides: dict[str, SkillVisibility] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BrowserConfig:
    """Ajan tarayıcısının (`browser_*`) profil ve pencere davranışı (P-023)."""

    #: Kapalıysa `browser_open` hiçbir profil yüklemez ve `profile` argümanını reddeder;
    #: `fusion browser` komutları yine çalışır (içe aktarma, listeleme).
    profiles_enabled: bool = True
    #: Açılışta kendiliğinden yüklenecek profil adı; boşsa çerezsiz (eski davranış).
    default_profile: str = ""
    #: Tarayıcı penceresi görünmez (true) ya da görünür (false) açılır.
    headless: bool = True
    #: Masaüstü Tarayıcı paneli (P-045): ajanın `browser_*` araçları paneldeki paylaşılan
    #: tarayıcıda çalışır (canlı izlenir, devralınır). false: tur başına ayrı başsız tarayıcı.
    panel_agent: bool = True


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    """Anlamsal arama için gömme sağlayıcısı."""

    #: "local" (ChromaDB gömülü ONNX, çevrimdışı) | "nim" (NVIDIA NIM, çok-dilli)
    provider: str
    #: NIM seçilirse kullanılacak model kimliği.
    model: str


class McpTransport(StrEnum):
    """MCP sunucusuna ulaşmak için kullanılan standart taşıma."""

    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"


class McpScope(StrEnum):
    """Sunucu kaydının yaşadığı yer (Claude Code `--scope`).

    `user`: kullanıcının `config.yaml`'ı (eski kayıtların tümü). `project`: proje kökündeki
    `.mcp.json` (Claude Code ile ortak biçim); yalnız güvenilen projede yüklenir ve
    `config.yaml`'a yazılmaz (P-049).
    """

    USER = "user"
    PROJECT = "project"
    #: Etkin bir eklentinin `.mcp.json`'ı (P-059); hiçbir ayar dosyasına yazılmaz.
    PLUGIN = "plugin"


class McpTrust(StrEnum):
    """OAuth veya bağlantı başarısı kaynak güveni yerine geçmez."""

    UNREVIEWED = "unreviewed"
    TRUSTED = "trusted"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    """Bağlanılacak dış MCP sunucusu; eski kayıtlar stdio olarak kalır.

    Burada tutulur (mcp SDK'sını import ETMEZ): yapılandırma, MCP kurulu olmadan da
    yüklenebilmeli. Bağlantıyı kuran `mcp_bridge` katmanı SDK'yı ayrıca ister."""

    name: str
    command: str = ""
    args: tuple[str, ...] = ()
    transport: McpTransport = McpTransport.STDIO
    url: str = ""
    scopes: tuple[str, ...] = ()
    client_id: str = ""
    #: stdio sunucusunun ihtiyaç duyduğu sırların yalnız ORTAM DEĞİŞKENİ adları.
    #: Değerler config'e girmez; şifreli depodan süreç ortamına yüklenir.
    env_names: tuple[str, ...] = ()
    #: Uzak sunucuya `Authorization: Bearer` ile gidecek token'ın ORTAM DEĞİŞKENİ adı.
    #
    # OAuth'a alternatif yoldur. Ölçüldü (mcp.facebook.com/ads): sunucu dinamik
    # istemci kaydını reddediyor, yani client_id olmadan OAuth hiç başlamıyor; aynı
    # sunucunun metadatası `bearer_methods_supported: ["header"]` diyor. Token dolu
    # olduğunda OAuth akışı HİÇ kurulmaz: giriş penceresi, client_id ve her tura
    # eklenen OAuth gecikmesi ortadan kalkar. Değer burada değil, `env_names` gibi
    # şifreli depoda durur.
    token_env: str = ""
    trust: McpTrust = McpTrust.UNREVIEWED
    reviewed_source: str = ""
    #: İncelendiği andaki araç tanımlarının özeti (`mcp_bridge.trust.tools_digest`). Boşsa araç
    #: tanımı denetlenmez (eski kayıtlar); doluysa tanım değişince güven düşer, yeniden onay ister.
    reviewed_tools: str = ""
    #: Verilmezse istemcinin mevcut ağ bütçesi kullanılır; ayrı sayı uydurulmaz.
    connect_timeout_s: float | None = None
    list_timeout_s: float | None = None
    call_timeout_s: float | None = None
    close_timeout_s: float | None = None
    #: None tur runtime retry dizisini kullanır; boş tuple backoff istemez.
    retry_delays_s: tuple[float, ...] | None = None
    #: Yalnız bu uzak araç adları kayıt defterine girer (uzak ad, `<sunucu>__` öneksiz).
    #: Boş = sunucunun bütün araçları. WordPress 63, GitHub 90+ araç sunar; kullanıcı
    #: işine yarayanları seçer (M1-12). Güven özeti (`reviewed_tools`) TÜM tanımlar üzerinden
    #: hesaplanır: izin listesi güvenin kapsamını daraltmaz.
    allowed_tools: tuple[str, ...] = ()
    #: İzin listesinden sonra sunucu başına en fazla bu kadar araç kaydedilir (sunucunun
    #: verdiği sırayla ilk N; fazlası günlüğe yazılır). `None` = sınır yok.
    max_tools: int | None = None
    #: Kaydın kaynağı: `user` (config.yaml) ya da `project` (.mcp.json). Yazıcılar kaydı
    #: yalnız kendi kapsamının dosyasına yazar (P-049).
    scope: McpScope = McpScope.USER
    #: Stdio sürecine verilecek SIR OLMAYAN ortam değerleri `(ad, değer)`; değer
    #: `${VAR:-varsayılan}` başvurusu taşıyabilir ve bağlantı anında çözülür. Sırlar buraya
    #: yazılmaz, `env_names` ile şifreli depodan gelir. `.mcp.json` `env` alanı buraya iner.
    env_literals: tuple[tuple[str, str], ...] = ()

    @property
    def secret_env_names(self) -> tuple[str, ...]:
        """Bu sunucunun sır taşıyan ortam değişkeni adları (değerler config'te değildir)."""
        return (*self.env_names, *((self.token_env,) if self.token_env else ()))


def mcp_secret_env_names(servers: Iterable[McpServerConfig]) -> frozenset[str]:
    """Tüm MCP sunucularının sır ortam adları.

    Sırlar süreç ortamında yaşar (MCP istemcisi oradan okur); araç/terminal çocuk süreçleri
    bunları miras almasın diye çocuk ortamından bu adlar çıkarılır.
    """
    return frozenset(name for server in servers for name in server.secret_env_names)


@dataclass(frozen=True, slots=True)
class HostedConnectorConfig:
    """Web sağlayıcısının KENDİ connector ekranından bağlanmış uzak MCP sunucusu.

    Fusion bu sunucuya MCP KONUŞMAZ. Araçlar sağlayıcının ajan döngüsünün içinde
    yaşar; Fusion onları zaten sürdüğü web oturumuna yazıp okuyarak kullanır
    (bkz. `mcp_bridge/hosted.py`).

    Neden bu model gerekli — ölçülmüş engel: Meta'nın barındırdığı MCP dinamik
    istemci kaydını reddediyor ve BAŞKALARININ reklam hesabına OAuth ile
    girebilmek Meta'da App Review istiyor. Buna karşılık aynı sunucu
    ChatGPT/Claude/Gemini'nin connector ekranından tek girişle bağlanabiliyor,
    çünkü o istemciler sunucu tarafında onaylı.
    """

    #: Kullanıcıya görünen ad; araç adlarının öneki de budur.
    name: str
    #: MCP adresi. Kullanıcı bunu sağlayıcının connector paneline yapıştırır.
    url: str
    #: Bu connector'ı barındıran web sağlayıcısı (`claude_web`, `chatgpt_web`, ...).
    provider: str
    #: Aynı sağlayıcıda birden çok oturumu ayıran etiket.
    account: str = "main"
    #: Keşif ÖLÇÜMÜ geçti mi?
    #
    # Varsayılan False ve bu bilinçli — `WebSessionConfig.tool_eval_passed` ile
    # aynı gerekçe: doğrulanmamış bir connector'ın araçlarını kayıt defterine
    # eklemek, modelin var olmayan yeteneklere güvenmesine yol açar.
    verified: bool = False


@dataclass(frozen=True, slots=True)
class WebSessionConfig:
    """Kullanıcının kendi web aboneliği veya yetkili OpenAI-uyumlu web ucu.

    `transport="http"` eski/kendi barındırılan OpenAI-uyumlu uçları korur.
    `transport="browser"` ise Fusion'ın izole Playwright profilini kullanarak ChatGPT,
    Claude, Gemini veya Copilot web arayüzünü native bir sağlayıcı gibi çalıştırır.

    Sır burada TUTULMAZ. API token'ı `auth_env`, web Cookie başlığı ise
    `credential_ref` ile şifreli depodan çözülür.
    """

    #: Zincirde/rolde kullanılan kararlı model kimliği.
    model: str
    #: Genel HTTP transport için `/chat/completions` ucu. Browser transport'ta boş.
    endpoint: str = ""
    #: `custom`, `chatgpt_web`, `claude_web`, `gemini_web`, `copilot_web`.
    provider: str = "custom"
    #: Aynı sağlayıcıda birden çok oturumu ayıran kullanıcı etiketi.
    account: str = "main"
    #: `http` ya da `browser`.
    transport: str = "http"
    #: Bearer token'ın ortam değişkeni adı (yalnız genel HTTP ucu için).
    auth_env: str | None = None
    #: Cookie başlığının şifreli depodaki anahtarı; değerin kendisi config'e girmez.
    credential_ref: str | None = None
    #: Araç desteği: "none" ya da "emulated".
    tool_support: str = "none"
    #: Taklit araç çağrısı değerlendirmesini GEÇTİ mi? (bkz. `tools.emulation_eval`)
    #:
    #: Varsayılan False ve bu bilinçli: doğrulanmamış bir taklit-araç modeli dosya
    #: değiştiren agent OLAMAZ. Model araç çağrısını metin olarak üretir; biçimi
    #: tutturamadığında sessizce yanlış dosyaya yanlış içerik yazma riski doğar.
    #: Panel değerlendirmeyi çalıştırıp bu alanı yazar.
    tool_eval_passed: bool = False
    tool_evaluated_at: float | None = None
    tool_evaluation_scope: str = ""
    tool_evaluation_adapter_revision: str = ""
    #: Son gerçek küçük istek başarıyla tamamlandı mı? Profil klasörü bunu kanıtlamaz.
    login_verified: bool = False
    #: Tur tarayıcısının pencere kipi: `visible`, `headless` ya da `hidden`.
    #:
    #: Alan adı `headless` OLARAK KALIR ve eski dosyalar bozulmaz: `WindowMode` bir
    #: `IntEnum` olduğu için `headless: true` → `HEADLESS`, `headless: false` →
    #: `VISIBLE` diye okunur. Üçüncü kip `headless: hidden` yazılarak seçilir.
    headless: WindowMode = WindowMode.HEADLESS
    #: Web UI çağrısı için üst süre sınırı.
    timeout_s: float = 180.0
    #: Kullanıcı bu oturumu geçici olarak kapatabilir.
    enabled: bool = True
    #: Sağlayıcının kendi arayüzünde doğrulanmış model/kip etiketi. Boşsa otomatik.
    selected_model: str = ""


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
    #: Öğretmen rolü — `ask_teacher` aracının danıştığı web oturumu (ChatGPT/Gemini
    #: web). Kullanıcının kendi web girişine bağlı olduğu için opsiyoneldir; tanımlı
    #: değilse ya da eşleşen `web_sessions` girişi giriş yapılmamışsa araç
    #: `ConfigError` ile anlaşılır bir mesaj verir (bkz. `engine_tools.py`).
    teacher: ModelSpec | None = None
    #: Seçilebilir model kademeleri, `defaults.yaml`'daki yazım SIRASIYLA. Sıra
    #: anlamlıdır: seçim ekranı bu sırayı gösterir ve renk geçişini buna yayar.
    tiers: tuple[TierSpec, ...] = ()
    #: Profil adı → uygunluk eşikleri. Model seçim ekranı aktif profile göre bu
    #: eşiklerle süzülür. Tanımsızsa filtre uygulanmaz (özellik sessizce kapanır).
    profile_eligibility: dict[str, ProfileEligibility] = field(default_factory=dict)
    #: Ajanın bağlanacağı dış MCP sunucuları. Boşsa MCP istemcisi hiç kurulmaz.
    mcp_servers: tuple[McpServerConfig, ...] = ()
    #: Kullanıcının yetkili olduğu web (oturum tabanlı) uçlar. Boşsa özellik kapalı;
    #: tanımlıysa eşleşen model kimlikleri API yerine web transport'uyla karşılanır.
    web_sessions: tuple[WebSessionConfig, ...] = ()
    #: Web sağlayıcısının connector ekranından bağlanmış uzak MCP sunucuları.
    hosted_connectors: tuple[HostedConnectorConfig, ...] = ()
    #: Ajan tarayıcısı profil/pencere ayarları; eski yapılandırmada yoksa varsayılanlar.
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    #: Beceri/ajan kataloğu tercihleri.
    capabilities: CapabilitiesConfig = field(default_factory=CapabilitiesConfig)
    #: `run_shell` sandbox politikası (P-010); kip `runtime.shell_sandbox`'tadır.
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    #: Bilgisayar kullanımı (`desktop:`, P-006); eski yapılandırmada yoksa varsayılanlar.
    desktop: DesktopSettings = field(default_factory=DesktopSettings)

    def candidate_by_name(self, name: str) -> ModelSpec | None:
        """Ada göre aday bul; yoksa None."""
        return next((item for item in self.candidates if item.name == name), None)

    def tier_by_name(self, name: str) -> TierSpec | None:
        """Ada göre kademe bul (büyük/küçük harf duyarsız); yoksa None."""
        wanted = name.strip().lower()
        return next((item for item in self.tiers if item.name == wanted), None)


def hosted_connector_ready(config: Config, connector: HostedConnectorConfig) -> bool:
    """Connector'ı taşıyacak web oturumu var ve kullanılabilir mi?

    Sağlayıcı-barındırmalı connector yalnız o sağlayıcının oturumu AÇIKKEN
    çalışır: araçlar Fusion'da değil sağlayıcının ajan döngüsünde yaşar. Bu yüzden
    "çalışabilir mi" sorusu bir tahmin değil, yapılandırmadan okunan bir olgudur —
    arayüz uyarısını da bu fonksiyon besler.
    """
    return any(
        session.provider == connector.provider
        and session.account == connector.account
        and session.transport == "browser"
        and session.enabled
        and session.login_verified
        for session in config.web_sessions
    )

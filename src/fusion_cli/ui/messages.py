"""Kullanıcıya görünen tüm Türkçe metinlerin tek kaynağı.

Kod içine string gömülmez: bir metni değiştirmek tek dosyada tek satır değiştirmektir,
aynı mesajın iki farklı varyantı oluşamaz ve ileride ikinci bir dil eklemek bu dosyanın
bir eşdeğerini yazmaktan ibaret olur.

Şablonlar `str.format` alanları kullanır; biçimlendirme çağrı yerinde yapılır.
"""

from __future__ import annotations

# --- Genel ---------------------------------------------------------------- #
APP_TAGLINE = "ücretsiz LLM füzyonu · hakem · öz-öğrenen"
VERSION = "fusion-cli {version}"

# --- Durum ---------------------------------------------------------------- #
STATUS_THINKING = "düşünüyor…"
# Kimlik olarak rol adı değil, cevabı gerçekten veren MODEL yazılır: yedeğe
# düşülen turda rol adı değişmediği için ekran seçilen modeli göstermeye devam
# ediyor ve yanlış model sessizce çalışıyordu.
MODEL_CALL_OK = "{model} · {duration} · {tokens} token"
MODEL_CALL_FAILED = "{model} · {error}"
MODEL_FALLBACK = "yedek devrede: {requested} → {fallback} · {reason}"

# --- Hata ----------------------------------------------------------------- #
ERROR_PREFIX = "hata"
ERROR_NO_ANSWER = "Hiçbir model yanıt veremedi. Ağ bağlantısını ve API anahtarını kontrol et."
# İki sağlayıcının sınırı FARKLI ÇALIŞIR ve tavsiye buna göre değişir:
#
# - OpenRouter: sınır HESAP başınadır (20 istek/dk; günlük 50, $10 kredi varsa
#   1000). Model değiştirmek işe yaramaz.
# - NVIDIA NIM: sınır MODEL BAŞINADIR — ölçüldü (2026-07-26): aynı anahtarla aynı
#   saniyede nemotron-super 429 verirken deepseek-v4-flash çalışıyordu. Burada
#   başka bir modele geçmek GERÇEKTEN işe yarar.
#
# Bu yüzden mesaj ikisini ayırır; tek bir "kota doldu" cümlesi birinde yanlış
# tavsiye olurdu.
ERROR_RATE_LIMITED = (
    "Sağlayıcı hız sınırına takıldı ve zincirdeki tüm modeller denendi.\n"
    "  · NVIDIA NIM'de sınır MODEL BAŞINADIR: `/level` ile başka bir kademe "
    "seçmek çoğu zaman anında çözer.\n"
    "  · OpenRouter'da sınır HESAP başınadır (20 istek/dk, 50 istek/gün); model "
    "değiştirmek açmaz — bir dakika bekle ya da hesabına $10 kredi yükle "
    "(günlük 1000 isteğe çıkar).\n"
    "  · `/provider` ile tek sağlayıcıya kilitlenirsen ötekinin kotası korunur."
)
ERROR_CONFIG = "Yapılandırma hatası: {detail}"
ERROR_INTERRUPTED = "işlem durduruldu"

# --- config show ---------------------------------------------------------- #
CONFIG_SOURCE_DEFAULTS = "yalnızca gömülü varsayılanlar (kullanıcı dosyası yok)"
CONFIG_SOURCE_FILE = "kullanıcı dosyası: {path}"
CONFIG_HEADING_CANDIDATES = "Fusion adayları"
CONFIG_HEADING_JUDGE = "Hakem / sentez"
CONFIG_HEADING_AGENT = "Agent modeli"
CONFIG_HEADING_RUNTIME = "Çalışma zamanı"
CONFIG_FALLBACK_NONE = "(yedek tanımlı değil)"

# --- Fusion --------------------------------------------------------------- #
FUSION_CANDIDATES = "{count} model düşünüyor · {names}"
FUSION_JUDGING = "hakem…"
FUSION_JUDGING_AND_SYNTHESIZING = "hakem + sentez…"

FUSION_WINNER = "kazanan: {winner}"
FUSION_SYNTHESIZED = "sentez · adayların en iyi yanlarının birleşimi"
FUSION_SINGLE = "tek geçerli cevap; hakem atlandı"
FUSION_JUDGE_FALLBACK = "hakem yetişemedi; ilk geçerli aday seçildi"

FUSION_CANDIDATE_SUMMARY = "adaylar:"
FUSION_SCORE_TABLE_MODEL = "Model"
FUSION_SCORE_TABLE_SCORE = "Puan"
FUSION_ALL_ANSWERS = "{name} · {duration}"

# --- Agent ---------------------------------------------------------------- #
AGENT_TOOL_OK = "{name} {summary}"
AGENT_TOOL_FAILED = "{name} başarısız · {summary}"
#: Diff özeti — kaç satır eklendi/silindi (Claude Code "N additions, M removals").
DIFF_SUMMARY = "{added} ekleme, {removed} silme"
#: Diff tavana ulaştığında alta basılan kırpma satırı.
DIFF_TRUNCATED = "… (+{count} satır daha)"
AGENT_SUBAGENT_STARTED = "alt-ajan devraldı: {task}"
AGENT_SUBAGENT_FINISHED = "alt-ajan bitti · {count} araç çağrısı"
AGENT_COUNCIL = "council: çoklu modele danışılıyor…"
AGENT_SELF_REVIEW_CLEAN = "öz-denetim · sorun yok"
AGENT_SELF_REVIEW_ISSUE = "öz-denetim · sorun bulundu, düzeltiliyor"
AGENT_CONTEXT_COMPRESSED = "bağlam sıkıştırıldı ({before} → {after} mesaj)"
AGENT_EMPTY_ANSWER = "(model boş yanıt verdi)"

# --- Tur bütçesi ----------------------------------------------------------- #
#
# Tur bir bütçe sınırına çarparak bittiğinde kullanıcı SEBEBİNİ görür. Sessizce
# durmak, kullanıcının aynı isteği tekrar denemesine ve aynı döngüye yeniden
# girmesine yol açıyordu. Anahtarlar `core.budget.BudgetStop` değerleridir.
AGENT_BUDGET_REASONS = {
    "model_calls": "model çağrısı sınırına ulaşıldı ({model_calls}); tur sonlandırıldı",
    "tool_rounds": "araç turu sınırına ulaşıldı ({tool_rounds}); tur sonlandırıldı",
    "deadline": "tur süre sınırına ulaştı ({elapsed_s:.0f} sn); sonlandırıldı",
    "no_progress": (
        "{idle_rounds} turdur ilerleme yok (ne başarılı araç sonucu ne dosya "
        "değişikliği); tur sonlandırıldı"
    ),
    "repeated_call": "aynı araç çağrısı değişiklik olmadan tekrarlandı; döngü sonlandırıldı",
    "contract_unrepairable": "model geçerli bir araç çağrısı üretemedi; tur sonlandırıldı",
    "empty_responses": "model arka arkaya boş yanıt döndürdü; tur sonlandırıldı",
}
#: Tanınmayan bir sebep gelirse sessiz kalınmaz.
AGENT_BUDGET_UNKNOWN = "tur bütçesi doldu ({reason}); sonlandırıldı"

# --- Çalışma göstergesi ---------------------------------------------------- #
WORK_TOKENS = "↑ {count} token"
#: Spinner'ın parantezindeki kesme ipucu. Claude Code "esc to interrupt" yazar; fusion'da
#: çalışan turu Ctrl-C keser (bkz. repl/loop `_cancel_on_interrupt`), esc değil — bu yüzden
#: gerçekten çalışan kısayol gösterilir.
WORK_INTERRUPT = "durdurmak için Ctrl-C"
#: TUI'de kesme ipucu — orada esc turu gerçekten keser.
WORK_INTERRUPT_ESC = "durdurmak için esc"
#: Tur çalışırken gönderilen satır kuyruğa alınınca gösterilen bildirim.
TUI_QUEUED = "sıraya alındı: {line}"
WORK_THINKING = "hazırlanıyor…"
#: Görünür düşünme bloğunun başlığı (Claude Code "✻ Thinking…"). `/thinking` açıkken basılır.
THINKING_HEADER = "düşünüyor…"
WORK_CANDIDATES = "{count} model düşünüyor…"
WORK_JUDGING = "hakem değerlendiriyor…"
WORK_SYNTHESIZING = "hakem + sentez çalışıyor…"
WORK_TOOL = "{name} çalışıyor…"
WORK_SUBAGENT = "alt-ajan çalışıyor…"
WORK_COUNCIL = "çoklu modele danışılıyor…"
WORK_REVIEW = "öz-denetim…"
AGENT_LESSONS_RECALLED = "{count} ilgili ders hatırlandı"
AGENT_LESSONS_LEARNED = "{count} yeni ders belleğe kazındı"

# --- Bellek --------------------------------------------------------------- #
MEMORY_UNAVAILABLE = "bellek kullanılamıyor, öğrenme kapalı: {reason}"
MEMORY_DISABLED = "bellek kapalı (--no-memory)"
MEMORY_EMPTY_STATS = "Henüz performans kaydı yok. Önce birkaç `fusion run` çalıştır."
MEMORY_EMPTY_LESSONS = "Henüz ders yok. `fusion memory seed` ile başlangıç derslerini yükle."
MEMORY_SEEDED = "{count} yeni küratörlü ders yüklendi ({total} tanenin içinden)."
MEMORY_REINDEXED = (
    "{total} parça indekslendi (+{added} yeni, -{removed} eski, {unchanged} değişmemiş)."
)
MEMORY_FEEDBACK_APPLIED = "'{model}' modeline '{verdict}' geri bildirimi işlendi ({task_type})."
MEMORY_FEEDBACK_MISSING = "Bu görev tipi ve model için kayıt bulunamadı."
MEMORY_LOCATION = "bellek dizini: {path}"

# --- Maliyet ve izleme ----------------------------------------------------- #
COST_TITLE = "Oturum kullanımı"
COST_TABLE_ROLE = "Rol"
COST_TABLE_CALLS = "Çağrı"
COST_TABLE_PROMPT = "Girdi"
COST_TABLE_COMPLETION = "Çıktı"
COST_TABLE_COST = "Maliyet"
COST_TOTAL = "toplam: {calls} çağrı · {tokens} token · ${cost:.4f}"
COST_FREE_NOTE = "yapılandırılmış modeller ücretsiz olduğu için maliyet 0 görünür"
COST_EMPTY = "Henüz model çağrısı yapılmadı."
TRACING_ENABLED = "Langfuse izleme açık"
TRACING_DISABLED = "Langfuse izleme kapalı: {reason}"
CATALOG_OPENROUTER = "OpenRouter — ücretsiz modeller"
CATALOG_NIM = "NVIDIA NIM — kataloğundaki modeller"
CATALOG_EMPTY = "alınamadı (ağ ya da anahtar yok)"

MEMORY_TABLE_TITLE = "Model performansı (fusion öz-öğrenmesi)"
LESSON_TABLE_TITLE = "Öğrenilen dersler — {mistakes} kaçınılacak · {successes} uygulanacak"
MEMORY_TABLE_MODEL = "Model"
MEMORY_TABLE_SAMPLES = "Örnek"
MEMORY_TABLE_SCORE = "Ort. Puan"
MEMORY_TABLE_WINS = "Galibiyet"
MEMORY_TABLE_LATENCY = "Ort. Gecikme"
LESSON_TABLE_KIND = "Tür"
LESSON_TABLE_SOURCE = "Kaynak"
LESSON_TABLE_TEXT = "Ders"
LESSON_KIND_MISTAKE = "kaçın"
LESSON_KIND_SUCCESS = "uygula"
LESSON_SOURCE_SEED = "hazır"
LESSON_SOURCE_LEARNED = "öğrenildi"
LESSON_SOURCE_MANUAL = "elle"

# --- Onay ----------------------------------------------------------------- #
APPROVAL_TITLE = "onay gerekiyor · {tool}"
CONFIRM_QUESTION = "  onaylıyor musun? (e/h, Enter = evet)"
DANGER_WARNING = "⚠ geri alınamaz işlem: {reason}"
AGENT_ASKS = "agent soruyor"
ANSWER_PROMPT = "  cevabın"
NO_ANSWER_AVAILABLE = (
    "(kullanıcı cevap veremedi — etkileşimsiz ortam. Soru sormayı bırak, "
    "elindeki bilgiyle en makul kararı ver ve devam et.)"
)

# --- run ------------------------------------------------------------------ #
RUN_EMPTY_TASK = "Görev metni boş olamaz."
RUN_UNKNOWN_TASK_TYPE = "Bilinmeyen görev tipi: {given}. Geçerli olanlar: {valid}"
RUN_UNKNOWN_MODE = "Bilinmeyen onay modu: {given}. Geçerli olanlar: {valid}"
RUN_UNKNOWN_FEEDBACK = "Bilinmeyen geri bildirim: {given}. Geçerli olanlar: {valid}"


# --- REPL ------------------------------------------------------------------ #
REPL_GOODBYE = "görüşürüz"
REPL_ENGINE_AGENT = "motor → agent (araçlar + çok-turlu hafıza)"
REPL_ENGINE_FUSION = "motor → fusion (çoklu model + hakem + sentez)"
REPL_MODE_CHANGED = "onay modu → {mode}"
REPL_HISTORY_CLEARED = "sohbet geçmişi temizlendi ({count} mesaj)"
REPL_TASK_TYPE_CHANGED = "görev tipi → {task_type}"
REPL_SHOW_ALL = "tüm aday cevapları: {state}"
REPL_SHOW_THINKING = "model düşünmesini göster: {state}"
REPL_SYNTHESIS = "sentez: {state}"
REPL_ON = "açık"
REPL_OFF = "kapalı"
REPL_ON_OFF_HINT = "shift-tab mod · /help"
#: TUI'de girdinin altındaki durum satırının kısayol ipuçları (Claude Code stili).
TUI_STATUS_HINT = "shift-tab: mod · esc: durdur · pgup/mouse: geçmiş · /help"
#: Onay beklerken çalışma satırında gösterilen ipucu.
TUI_CONFIRM_HINT = "onay: e = evet · h/esc = hayır"
#: Onay önizlemesinin başındaki etiket.
TUI_CONFIRM_PREVIEW = "onay ister:"
#: Tam-ekran/TUI'de argümansız seçici komutu çağrılınca gösterilen yönlendirme.
TUI_PICKER_NEEDS_ARG = "/{name} bu görünümde argüman ister. Örnek: /level high. Ayrıntı: /help."

# --- Karşılama ekranı ------------------------------------------------------ #
APP_NAME = "Fusion CLI"
#: Karşılama kutusunun ilk satırındaki selamlama (Claude Code "Welcome to Claude Code!").
WELCOME_GREETING = "hoş geldin"
WELCOME_FIELD_ENGINE = "motor"
WELCOME_FIELD_APPROVAL = "onay"
WELCOME_FIELD_MODEL = "model"
WELCOME_FIELD_DIR = "dizin"
WELCOME_FIELD_MEMORY = "bellek"
WELCOME_MEMORY_ON = "açık · {count} ders"
WELCOME_MEMORY_OFF = "kapalı"

WELCOME_TIP_TITLE = "İpucu"
WELCOME_TIPS = (
    "Karmaşık bir görevde `shift-tab` ile `plan` moduna geç: Fusion önce planı "
    "çıkarır, sen onaylayınca uygular.",
    "Zor bir kararda agent'a `council` aracını kullandır: soruyu birden çok modele "
    "danışıp ortak akılla cevaplar.",
    "`/fusion` ile aynı soruyu üç modele birden sor; hakem en iyisini seçer, sentez "
    "hepsinin en iyi yanlarını birleştirir.",
    "`/learn <kural>` ile kalıcı bir kural öğret; Fusion benzer görevlerde bunu "
    "kendiliğinden hatırlar.",
    "`/memory reindex` ile kod tabanını indeksle; agent 'X nerede yapılıyor?' "
    "sorularını grep yerine anlamca cevaplar.",
    "Riskli bir işte `shift-tab` ile `security` moduna geç: her değişiklik diff "
    "önizlemesiyle tek tek onayına sunulur.",
    "`/model` ile oturum içinde model değiştirebilirsin; `fusion models --fetch` "
    "canlı katalogdan ücretsiz modelleri listeler.",
    "Uzun bir oturumda `/compact` ile geçmişi özetleyip bağlam limitinden tasarruf et.",
)

WELCOME_ABOUT_TEXT = (
    "Ücretsiz LLM'lerle çalışan bir kodlama asistanı. Dosya okur/yazar, komut "
    "çalıştırır, web'de arar; aynı soruyu birden çok modele paralel sorup hakemle "
    "en iyi cevabı seçer. Her görevden ders çıkarır ve benzer bir işte hatırlar."
)

WELCOME_START_TITLE = "Başlarken"
WELCOME_START_ITEMS = (
    ("mesaj yaz", "aktif motora gönderir"),
    ("/help", "tüm komutlar"),
    ("/agent · /fusion", "motor değiştir"),
    ("shift-tab", "onay modunu döndür"),
)

# --- /tips: verimli kullanım rehberi --------------------------------------- #
#
# Karşılama ekranındaki tek satırlık ipuçları rastgele döner ve bir bütün
# oluşturmaz. Burası ise komutları GÖREV EKSENİNDE anlatır: hangi durumda
# hangisine uzanılır. Yardım ekranı (`/help`) komutları LİSTELER; burası ne zaman
# kullanılacağını söyler — ikisi farklı sorulardır.
TIPS_TITLE = "Fusion'ı verimli kullanmak"
TIPS_INTRO = (
    "Aşağıdakiler sık karşılaşılan durumlar ve o durumda hangi komuta uzanacağın. "
    "Tüm komutların listesi için: /help"
)

#: (başlık, satırlar) — her satır (komut, ne zaman kullanılır).
TIPS_SECTIONS = (
    (
        "Hangi motor?",
        (
            ("/agent", "dosya değiştir, komut çalıştır, araç kullan — asıl iş motoru"),
            ("/fusion", "tek bir SORUYA en iyi cevabı al; üç model yarışır, hakem seçer"),
            ("", "kod yazdırıyorsan agent, fikir/karar soruyorsan fusion"),
        ),
    ),
    (
        "Model ve kota",
        (
            ("/level", "hız ↔ yetenek takası: low en hızlı, premium en yetenekli ama yavaş"),
            ("/provider", "tek sağlayıcıya kilitlen; ötekinin kotası hiç harcanmaz"),
            ("/development", "listeden ya da alias yazarak istediğin modeli seç"),
            ("", "kota hatası alıyorsan önce /provider, sonra /level low dene"),
        ),
    ),
    (
        "Güvenlik ve geri alma",
        (
            ("shift-tab", "onay modunu döndür: auto → plan → security"),
            ("plan modu", "önce planı gör, onaylayınca uygulansın — büyük değişikliklerde"),
            ("/undo", "son turun dosya değişikliklerini geri al"),
            ("--add-dir", "proje dışına erişim gerekiyorsa açıkça ver"),
        ),
    ),
    (
        "Kaliteyi yükseltmek",
        (
            ("/verify", "projeni tanıyıp test/lint kapısı kurar; her turdan sonra çalışır"),
            ("/learn <kural>", "kalıcı kural öğret; benzer görevlerde hatırlar"),
            ("/good · /bad", "fusion cevabına geri bildirim ver, model seçimi öğrensin"),
        ),
    ),
    (
        "Uzun oturumlar",
        (
            ("/compact", "geçmişi özetle, bağlam limitinden tasarruf et"),
            ("/reset", "sohbet geçmişini tamamen temizle"),
            ("/cost", "bu oturumda ne kadar token/çağrı harcandı"),
        ),
    ),
)

CMD_TIPS = "Fusion'ı verimli kullanmayı öğren"

WELCOME_ABILITY_TITLE = "Neler yapabilir"
WELCOME_ABILITY_ITEMS = (
    ("araçlar", "dosya, kabuk, web, görev listesi"),
    ("fusion", "3 model + hakem + sentez"),
    ("bellek", "öğrendiğini benzer görevde hatırlar"),
    ("güvenlik", "diff önizlemesi, yıkıcı komutta onay"),
)
REPL_UNKNOWN_COMMAND = "bilinmeyen komut: /{name} — komut listesi için /help"
REPL_TURN_CANCELLED = "tur durduruldu"
REPL_NO_FUSION_YET = "Önce bir fusion turu çalıştır (/fusion), sonra geri bildirim ver."
REPL_LEARN_USAGE = "Kullanım: /learn <kalıcı olarak hatırlanacak kural>"
REPL_LEARN_SAVED = "kural belleğe kaydedildi"
REPL_LEARN_DUPLICATE = "bu kural zaten bellekte"
REPL_LEARN_TASK_LABEL = "kullanıcının koyduğu kural"
REPL_COMPACTED = "bağlam sıkıştırıldı ({before} → {after} mesaj)"
REPL_NOTHING_TO_COMPACT = "sıkıştırılacak kadar uzun bir geçmiş yok"
REPL_BACKGROUND_WAIT = "arka plandaki öğrenme tamamlanıyor…"
REPL_HELP_TITLE = "Komutlar"
#: Grubu olmayan komutların `/help`'te toplandığı başlık.
HELP_GROUP_OTHER = "Genel"
REPL_STATUS_BAR = "{engine} · {approval} · {task_type} · {model}"
REPL_TAGLINE = "ücretsiz LLM füzyonu · araçlar · öz-öğrenen bellek"
REPL_MODEL_SET = "{role} modeli → {model}"
REPL_MODEL_ADDED = "aday eklendi: {name} ({model})"
REPL_MODEL_REMOVED = "aday çıkarıldı: {name}"
REPL_MACRO_STARTED = "{name} çalıştırılıyor…"
REPL_SCHEDULE_SET = "hatırlatma kuruldu: {seconds} saniye sonra"
REPL_SCHEDULE_USAGE = "Kullanım: /schedule <saniye>  (ör. /schedule 300)"
REPL_SCHEDULE_FIRED = "⏰ hatırlatma zamanı geldi"
REPL_MACRO_NEEDS_ARGUMENT = "/{name} bir görev metni ister. Örnek: /{name} <ne yapılacak>"
REPL_MODEL_USAGE = (
    "Kullanım: /model [agent|judge <id>] | [cand <ad|no> <id>] | "
    "[add <ad> <id> [etiket…]] | [rm <ad>]   ·   liste için: /model"
)
# --- Seçim ekranı ---------------------------------------------------------- #
PICKER_HINT = "↑↓ gez · Enter seç · Esc vazgeç"
PICKER_PLAIN_PROMPT = "Seçim (numara, boş bırakırsan vazgeçilir): "
PICKER_CANCELLED = "seçim yapılmadı"
PICKER_MORE_ABOVE = "   ↑ {count} satır daha"
PICKER_MORE_BELOW = "   ↓ {count} satır daha"

# --- Kademe seçimi (/level) ------------------------------------------------ #
LEVEL_TITLE = "Model kademesi seç"
LEVEL_APPLIED = "kademe → {name}  ·  agent: {model}"
LEVEL_SAVED = "kaydedildi: {path}"
LEVEL_SAVE_FAILED = "kademe uygulandı ama kaydedilemedi: {error}"

# --- Profil editörü (/profiles) -------------------------------------------- #
PROFILES_HEADER = "profiller (kademe · baş model):"
PROFILES_ROW = "  {name}  →  {model}"
PROFILES_EMPTY = "tanımlı profil yok."
PROFILES_EDIT_TITLE = "'{name}' profilinin baş modelini seç"
PROFILES_APPLIED = "profil '{name}' güncellendi  ·  baş model: {model}"
PROFILES_UNKNOWN = "'{name}' adlı profil yok. Geçerli: {known}"
PROFILES_INCOMPATIBLE = "UYUMSUZ — {reason}"
PROFILES_NO_ELIGIBLE = (
    "'{name}' için uygun aday yok. Uyumsuzları görmek için: /profiles edit {name} incompatible"
)
PROFILES_EDIT_USAGE = "kullanım: /profiles  ·  /profiles edit <profil> [incompatible]"
MCP_MISSING_DEP = "MCP için resmî SDK gerekli ama kurulu değil. Kur: pip install 'fusion-cli[mcp]'"
MCP_TOOLS_LOADED = "{count} dış MCP aracı bağlandı"
MCP_CONNECT_FAILED = "MCP sunucusuna bağlanılamadı: {error} — dış araçlar olmadan devam ediliyor"
MCP_NO_SERVERS = "Yapılandırılmış MCP sunucusu yok. config.yaml içine mcp_servers ekle."
CMD_PROFILES = "profilleri gör / düzenle: /profiles · /profiles edit <profil> [incompatible]"

# --- Execution profili (/mode) --------------------------------------------- #
MODE_TITLE = "Çalışma profili seç"
MODE_AUTO_LABEL = "auto"
MODE_AUTO_HINT = "görevi sınıflandırıp uygun profili her turda kendisi seçer"
MODE_AUTO_ON = "profil → auto: her tur göreve göre kademe seçilecek"
MODE_AUTO_SELECTED = "auto profil → {profile}  ({reason})"
MODE_UNKNOWN = "'{name}' adlı profil yok. Geçerli: auto, {known}"

# --- Tanınan sağlayıcılar (/providers) ------------------------------------- #
PROVIDERS_HEADER = "tanınan sağlayıcılar (tür · resmiyet · risk · durum):"
PROVIDERS_ROW = "  {name}  ·  {kind}  ·  {status}  ·  {risk}  ·  {state}"
PROVIDERS_CONFIGURED = "kurulu"
PROVIDERS_MISSING = "anahtar yok"
PROVIDERS_LOCAL = "yerel"
PROVIDERS_FRAMEWORK = "framework (adaptör yok)"
CRED_TITLE = "Hangi sağlayıcının anahtarı eklensin?"
CRED_PROMPT = "{name} anahtarını yapıştır (ekranda görünmez): "
CRED_SAVED = "{name} anahtarı şifreli olarak kaydedildi ({env}). Sonraki oturumda etkin."
CRED_NO_KEY = (
    "Şifreli sır deposu kapalı: önce FUSION_SECRET_KEY ortam değişkenini ayarla. "
    "Alternatif olarak anahtarı doğrudan .env dosyana yazabilirsin."
)

# --- Sağlayıcı sağlığı (/health) ------------------------------------------- #
HEALTH_EMPTY = "henüz sağlık verisi yok — bir tur çalıştırınca dolar."
HEALTH_HEADER = "sağlayıcı sağlığı (güvenilirlik · devre):"
HEALTH_ROW = "  {model}  ·  {score:.0%}  ·  {phase}"
#: Circuit breaker durumlarının Türkçe karşılığı.
HEALTH_PHASE = {"closed": "kapalı", "open": "AÇIK (atlanıyor)", "half_open": "yarı-açık"}

# --- Reasoning effort (/effort) -------------------------------------------- #
EFFORT_TITLE = "Reasoning yoğunluğu seç"
EFFORT_HINT_AUTO = "modele bırak — parametre gönderilmez"
EFFORT_APPLIED = "effort → {effort}"
EFFORT_APPLIED_DOWNGRADED = "effort → {effort} (model {mapped} olarak uygular)"
EFFORT_UNKNOWN = "'{name}' geçersiz. Geçerli: {known}"

# --- Sağlayıcı tercihi (/provider) ----------------------------------------- #
PROVIDER_TITLE = "Hangi sağlayıcı kullanılsın?"
PROVIDER_AUTO = "Otomatik (ikisi birden)"
PROVIDER_AUTO_HINT = "biri yavaşsa öteki devreye girer; iki kota da harcanabilir"
PROVIDER_NVIDIA = "Yalnızca NVIDIA NIM"
PROVIDER_NVIDIA_HINT = "OpenRouter'a hiç istek gitmez, günlük 50 isteği korunur"
PROVIDER_OPENROUTER = "Yalnızca OpenRouter"
PROVIDER_OPENROUTER_HINT = "NIM kredisi harcanmaz"
PROVIDER_APPLIED = "sağlayıcı → {name}  ·  agent: {model}"
PROVIDER_CURRENT = "şu anki sağlayıcı: {name}"
CMD_PROVIDER = "hangi sağlayıcının kullanılacağını seç (kota kontrolü)"

# --- Doğrulama kapısı (/verify) -------------------------------------------- #
VERIFY_TITLE = "Doğrulama planını onayla"
VERIFY_PLAN_HEADING = "Bu projede şu doğrulama komutları bulundu:"
VERIFY_ACCEPT = "Onayla ve kaydet"
VERIFY_ACCEPT_HINT = "her turdan sonra sırayla çalışır"
VERIFY_REJECT = "Vazgeç"
VERIFY_REJECT_HINT = "kapı kapalı kalır"
VERIFY_NOTHING_FOUND = (
    "Bu projede tanınan bir doğrulama aracı bulunamadı.\n"
    "Komutları config.yaml içinde runtime.verification_commands altına elle yazabilirsin."
)
VERIFY_ACTIVE = "Doğrulama kapısı zaten kurulu:\n{commands}"
VERIFY_APPLIED = "Doğrulama kapısı açıldı. Her turdan sonra sırayla çalışacak:\n{commands}"
VERIFY_SAVE_FAILED = "kapı bu oturumda açıldı ama kaydedilemedi: {error}"

# --- Geliştirme modu (/development) ---------------------------------------- #
DEV_SOURCE_TITLE = "Model kaynağı seç"
DEV_SOURCE_OPENROUTER_FREE = "OpenRouter modelleri (ücretsiz)"
DEV_SOURCE_NIM_FREE = "NVIDIA modelleri (ücretsiz)"
DEV_SOURCE_OPENROUTER_PAID = "OpenRouter modelleri (ücretli)"
DEV_SOURCE_CUSTOM = "Özel model"
DEV_SOURCE_CUSTOM_HINT = "istediğin modelin alias'ını gir"
DEV_MODEL_TITLE = "Model seç — {source}"
DEV_CUSTOM_PROMPT = "Model alias'ı (biçim: <sağlayıcı>/<model>): "
DEV_EMPTY_CATALOG = (
    "katalog boş döndü. Ağ erişimi yoksa ya da bu kaynak anahtar istiyorsa "
    "(NVIDIA için NVIDIA_NIM_API_KEY) liste alınamaz."
)
DEV_PAID_WARNING = "dikkat: ücretli model seçtin, çağrılar faturalandırılır"
DEV_APPLIED = "model → {model}  ·  agent, hakem ve havuzun tamamı"
#: Katalog satırında modelin uygun olduğu profiller. Küçük bağlamlı model üst
#: profillerde görünmez; kullanıcı hangi profillere yaradığını satırda görür.
DEV_PROFILE_BADGE = "profiller: {profiles}"

REPL_PASTE_FOLDED = "⧉ {count} satır yapıştırıldı [#{index}]"
REPL_PASTE_FOLDED_CHARS = "⧉ {count} karakter yapıştırıldı [#{index}]"

# --- Komut açıklamaları ---------------------------------------------------- #
CMD_HELP = "komut listesini göster"
CMD_EXIT = "çıkış"
CMD_CLEAR = "ekranı temizle"
CMD_AGENT = "agent motoruna geç (araçlarla iş yapar)"
CMD_FUSION = "fusion motoruna geç (çoklu model + hakem)"
CMD_AUTO = "değiştirici işlemlere otomatik onay (yıkıcı komutta yine sorar)"
CMD_PLAN = "hiçbir değişiklik yapma, yalnızca planla"
CMD_SECURITY = "her değiştirici işlemi tek tek sor"
CMD_RESET = "agent sohbet geçmişini temizle"
CMD_COMPACT = "uzun geçmişi özetleyerek kısalt"
CMD_TASK_TYPE = "fusion görev tipi (general | code | reasoning | agent)"
CMD_SHOW_ALL = "tüm aday cevaplarını göster/gizle"
CMD_SHOW_THINKING = "model düşünmesini göster/gizle (Claude Code stili)"
CMD_SYNTHESIS = "sentezi aç/kapa"
CMD_GOOD = "son fusion kazananına olumlu geri bildirim"
CMD_BAD = "son fusion kazananına olumsuz geri bildirim"
CMD_REVISE = "son fusion kazananına düzeltme gerektiren geri bildirim"
CMD_LEARN = "kalıcı bir kural öğret"
CMD_SEED = "küratörlü başlangıç derslerini yükle"
CMD_REINDEX = "kod tabanını anlamsal indeksle"
CMD_STATS = "model performans tablosu"
CMD_LESSONS = "öğrenilen dersler"
CMD_MODELS = "yapılandırılmış modeller"
CMD_COST = "oturumda harcanan token ve tahmini maliyet"
CMD_MODEL = "oturum içinde model değiştir (argümansız: etkin modeller)"
UNDO_NOTHING = "Geri alınacak bir değişiklik yok."
UNDO_DONE = "{count} dosya son turdan önceki hâline döndürüldü:\n{paths}"
UNDO_PARTIAL = (
    "{count} dosya geri alındı; {failed} dosya geri alınamadı (izin ya da silinmiş dizin)."
)
CMD_UNDO = "son agent turunun dosya değişikliklerini geri al"
CMD_VERIFY = "doğrulama kapısını projeden keşfet ve aç"
CMD_MODE = "çalışma profili seç: auto · low · medium · high · max"
CMD_EFFORT = "reasoning yoğunluğu: auto · low · medium · high · xhigh · max"
CMD_HEALTH = "sağlayıcı sağlığı: güvenilirlik skoru ve circuit breaker durumu"
CMD_PROVIDERS = "tanınan sağlayıcılar: tür, resmiyet, risk ve kurulu mu"
CMD_LEVEL = "model kademesi seç: low · medium · high · ultra · premium"
CMD_DEVELOPMENT = "kaynak seçerek model değiştir (ücretsiz/ücretli katalog ya da özel alias)"
CMD_GOAL = "hedef kipi: görev bitene kadar pes etme"
CMD_GRILL = "mülakat kipi: kod yazmadan önce gereksinimleri sor"
CMD_BUG = "hata avı: bul, kök nedeni tespit et, düzelt, doğrula"
CMD_COMMIT = "değişiklikleri incele ve conventional commit ile kaydet"
CMD_REVIEW = "mevcut değişiklikleri güvenlik ve mimari açısından incele"
CMD_BROWSER = "web'de araştır ve kaynaklarıyla özetle"
CMD_SCHEDULE = "N saniye sonra hatırlatma kur"


# --- setup ----------------------------------------------------------------- #
SETUP_CREATED = "oluşturuldu: {path}"
SETUP_EXISTS = "zaten var, dokunulmadı: {path}"
SETUP_NEXT_STEPS = "Sırada:"
SETUP_STEP_KEYS = "anahtarlarını gir → {path}"
SETUP_STEP_RUN = "herhangi bir proje dizininde `fusion` yaz"
SETUP_PATHS = "kullanılan yollar:"

# --- fusion update / uninstall --------------------------------------------- #
MAINT_METHOD = "Fusion `{method}` ile kurulmuş."
MAINT_DATA_KEPT = (
    "Yapılandırman, API anahtarların ve öğrenilen dersler KORUNDU. "
    "Onları da silmek için: fusion uninstall --purge"
)
MAINT_REMOVED = "silindi:"
MAINT_NOTHING_TO_PURGE = "silinecek kullanıcı verisi yok."

# --- PATH kurulumu --------------------------------------------------------- #
PATH_MISSING = "`fusion` komutu PATH'te değil ({bin_dir} eksik)."
PATH_ASK = "Bu satırı {file} dosyana ekleyebilirim."
PATH_PROMPT = "Ekleyeyim mi? (E/h): "
PATH_ADDED = "PATH satırı eklendi: {file}"
PATH_RELOAD = "Yeni bir terminal aç ya da: source {file}"
PATH_SKIPPED = "Eklenmedi. Şu satırı kendin ekleyebilirsin:"
PATH_FAILED = "PATH satırı yazılamadı ({error}). Şunu kendin ekle:"

# --- fusion doctor --------------------------------------------------------- #
DOCTOR_STATE = {
    "ready": "Kurulum hazır. Başlatmak için: fusion",
    "partially_ready": "Kurulum kısmen hazır: agent çalışır, fusion motoru eksik.",
    "not_ready": "Kurulum hazır DEĞİL.",
}

# --- Kurulum sihirbazı ----------------------------------------------------- #
SETUP_WELCOME = "Fusion kurulumu — iki soru, sonra hazırsın."
SETUP_ASK_OPENROUTER = (
    "OpenRouter API anahtarı (önerilen — Enter ile atla)\n"
    "  Ücretsiz almak için: https://openrouter.ai/keys\n"
    "  Anahtar: "
)
SETUP_ASK_NIM = (
    "NVIDIA NIM API anahtarı (Enter ile atla)\n"
    "  Ayrı bir ücretsiz kotadan çalışır: https://build.nvidia.com/\n"
    "  Anahtar: "
)
SETUP_CANCELLED = "kurulum iptal edildi; hiçbir dosya değiştirilmedi"
SETUP_WRITE_FAILED = "anahtarlar yazılamadı: {path}"
SETUP_KEY_REQUIRED = "En az BİR anahtar gerekli; ikisi de boşken hiçbir model çağrılamaz."
SETUP_KEYS_SAVED = "anahtarlar kaydedildi: {path}"
SETUP_LESSONS_SEEDED = "{count} hazır ders belleğe yüklendi — eğitilmiş başlıyorsun"
SETUP_LESSONS_SKIPPED = (
    "hazır dersler yüklenemedi ({reason}); `fusion memory seed` ile deneyebilirsin"
)
SETUP_DONE = "Kurulum tamam. Herhangi bir proje dizininde `fusion` yaz."
SETUP_NO_KEYS = (
    "API anahtarı bulunamadı. `fusion setup` çalıştır ya da .env dosyana OPENROUTER_API_KEY yaz."
)
SETUP_ACTIVE_PROVIDERS = "kurulu sağlayıcılar: {names}"

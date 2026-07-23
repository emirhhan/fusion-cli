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
MODEL_CALL_STARTED = "{role} çalışıyor · {model}"
MODEL_CALL_OK = "{role} yanıtladı · {latency} ms · {tokens} token"
MODEL_CALL_FAILED = "{role} yanıt veremedi · {error}"

# --- Hata ----------------------------------------------------------------- #
ERROR_PREFIX = "hata"
ERROR_NO_ANSWER = "Hiçbir model yanıt veremedi. Ağ bağlantısını ve API anahtarını kontrol et."
ERROR_RATE_LIMITED = (
    "Ücretsiz kota doldu (sağlayıcı hız sınırı). Bir süre bekle ya da "
    "config.yaml içinde farklı bir ücretsiz model tanımla."
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
FUSION_CANDIDATES = "{count} model düşünüyor: {names}"
FUSION_JUDGING = "hakem değerlendiriyor…"
FUSION_JUDGING_AND_SYNTHESIZING = "hakem ve sentez paralel çalışıyor…"

FUSION_WINNER = "kazanan: {winner}"
FUSION_SYNTHESIZED = "sentezlenmiş cevap (adayların en iyi yanlarının birleşimi)"
FUSION_SINGLE = "tek geçerli cevap; hakem atlandı"
FUSION_JUDGE_FALLBACK = "hakem yetişemedi; ilk geçerli aday seçildi"

FUSION_CANDIDATE_SUMMARY = "adaylar:"
FUSION_SCORE_TABLE_MODEL = "Model"
FUSION_SCORE_TABLE_SCORE = "Puan"
FUSION_ALL_ANSWERS = "{name} · {latency} ms"

# --- Agent ---------------------------------------------------------------- #
AGENT_TOOL_OK = "{name} {summary}"
AGENT_TOOL_FAILED = "{name} başarısız · {summary}"
AGENT_SUBAGENT_STARTED = "alt-ajan devraldı: {task}"
AGENT_SUBAGENT_FINISHED = "alt-ajan bitti · {count} araç çağrısı"
AGENT_COUNCIL = "council: çoklu modele danışılıyor…"
AGENT_SELF_REVIEW_STARTED = "öz-denetim çalışıyor…"
AGENT_SELF_REVIEW_CLEAN = "öz-denetim: sorun yok"
AGENT_SELF_REVIEW_ISSUE = "öz-denetim bir sorun buldu; düzeltiliyor…"
AGENT_CONTEXT_COMPRESSED = "bağlam sıkıştırıldı ({before} → {after} mesaj)"
AGENT_STEP_LIMIT = "adım sınırına ulaşıldı ({limit}); tur sonlandırıldı"
AGENT_EMPTY_ANSWER = "(model boş yanıt verdi)"
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

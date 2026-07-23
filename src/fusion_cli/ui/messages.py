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
CONFIG_HEADING_AGENT = "Agent modeli"
CONFIG_HEADING_RUNTIME = "Çalışma zamanı"
CONFIG_FALLBACK_NONE = "(yedek tanımlı değil)"

# --- run ------------------------------------------------------------------ #
RUN_EMPTY_TASK = "Görev metni boş olamaz."

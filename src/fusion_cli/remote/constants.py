"""Uzaktan servis sabitleri. Değerler gerekçesiyle seçilmiştir; keyfi değildir."""

from __future__ import annotations

#: RPC sözleşme sürümü; yol öneki ve yanıt zarfı bununla gelir.
RPC_VERSION = "v1"

#: Eşleştirme kodu ömrü. Kısa tutulur: kod yalnız kullanıcı masaüstünde onaylarken geçerlidir.
PAIRING_CODE_TTL_SECONDS = 120
#: Kod alfabesi: 0/O ve 1/I karışmasın diye çıkarıldı. 8 karakter ≈ 40 bit.
PAIRING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 8
#: Onaylanmış eşleştirmenin cihaz tarafından alınabileceği süre.
PAIRING_CLAIM_TTL_SECONDS = 120

#: İmzalı isteğin saat sapması toleransı.
SIGNATURE_MAX_SKEW_SECONDS = 60
#: Nonce önbelleği tolerans penceresinin iki katı tutulur; yeniden oynatma bu aralıkta yakalanır.
NONCE_RETENTION_SECONDS = SIGNATURE_MAX_SKEW_SECONDS * 2
NONCE_CACHE_LIMIT = 10_000

#: Başarısız kimlik doğrulamada kilitlenme eşiği ve süresi.
AUTH_FAILURE_LIMIT = 5
AUTH_FAILURE_WINDOW_SECONDS = 300
AUTH_LOCKOUT_SECONDS = 900

#: Cihaz sırrı baytı (256 bit).
DEVICE_SECRET_BYTES = 32
#: İstek gövdesi üst sınırı; bellek şişirme saldırısına karşı.
MAX_BODY_BYTES = 256 * 1024
#: Görev başına tutulan olay sayısı üst sınırı.
MAX_EVENTS_PER_TASK = 5_000
#: Bildirim özeti uzunluğu: kod/özel içerik sohbet kanalına dökülmesin.
NOTIFICATION_SUMMARY_LIMIT = 280

#: Telegram: uzun yoklama süresi ve hız sınırı.
TELEGRAM_POLL_TIMEOUT_SECONDS = 25
TELEGRAM_FAILED_PAIR_LIMIT = 5

#: Varsayılan dinleme adresi: internete açık bind varsayılan değildir.
DEFAULT_REMOTE_HOST = "127.0.0.1"
DEFAULT_REMOTE_PORT = 8791

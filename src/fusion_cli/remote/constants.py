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
#: 1 MiB: telefondan küçültülmüş görsel/dosya eki (base64 ile ~%33 şişer) tek istekte sığsın.
MAX_BODY_BYTES = 1024 * 1024
#: Yüklenen ek üst sınırı (çözülmüş bayt); gövde sınırının altında kalır.
MAX_UPLOAD_BYTES = 700 * 1024
#: Yüklenen eklerin saklanma süresi; eski ekler yeni yüklemede temizlenir.
UPLOAD_RETENTION_SECONDS = 7 * 24 * 3600
#: Telefona gösterilecek görselin üst boyutu (çözülmüş bayt).
MEDIA_MAX_BYTES = 4 * 1024 * 1024
#: Akan yanıt parçalarının en sık birleştirme aralığı: saniyede en fazla ~4 olay.
DELTA_FLUSH_SECONDS = 0.25
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

#: Canlı ekran (görüntü akışı). Onaylı oturum KARE ÇEKİLDİKÇE uzar: telefon bu süre boyunca hiç kare
#: istemezse (uyku, ağ yok) oturum kapanır. Mutlak 5 dk sınırı akışı kullanım ortasında kesiyordu.
SCREEN_IDLE_TTL_SECONDS = 600
#: Kare çekilse bile bir oturumun yaşayabileceği en uzun süre; sonra yeniden onay gerekir.
SCREEN_MAX_SESSION_SECONDS = 7200
#: Onaylanmamış isteğin bekleme süresi.
SCREEN_REQUEST_TTL_SECONDS = 300
#: Kareler arası en az 0,5 sn, JPEG genişlik sınırı.
SCREEN_MIN_FRAME_INTERVAL_SECONDS = 0.5
SCREEN_MAX_WIDTH = 1280
SCREEN_JPEG_QUALITY = 60

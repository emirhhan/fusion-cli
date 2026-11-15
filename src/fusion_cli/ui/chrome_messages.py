"""CLI'de Chrome bağlantısının (`--chrome`, `/chrome`) kullanıcıya görünen metinleri (#421)."""

from __future__ import annotations

CMD_CHROME = "Chrome bağlantısı: durum, yeniden bağlan, tarayıcı seç, varsayılan aç/kapat"
CHROME_USAGE = "[status|reconnect|select|default on|off|install|permissions]"

PROJECT_IGNORED = (
    "Fusion bu projenin ayarlarındaki CLAUDE_CODE_ENABLE_CFC değerini yok saydı: bir proje "
    "Chrome'u (Fusion Browser) açamaz. Kendin açmak için /chrome çalıştır ya da --chrome ile "
    "başlat."
)

INTRO_TITLE = "Chrome'da Fusion"
INTRO_BODY = (
    "Fusion, Chrome'daki Fusion Browser eklentisiyle senin tarayıcında çalışabilir: sekme açar, "
    "sayfayı okur, tıklar ve yazar; açık oturumlarını paylaşır. Giriş sayfası ya da CAPTCHA "
    "çıkınca durur ve senden ister.\n\n"
    "Site izinleri: bir sitede ilk tarayıcı eyleminden önce Fusion izin sorar; o site için "
    "oturum boyu izin verebilirsin. İzinleri /chrome permissions ile yönetirsin."
)
INTRO_CONTINUE = "Devam etmek için Enter'a bas"

DETECTED_TITLE = "Chrome'da Fusion Browser eklentisi bulundu"
DETECTED_YES = "Evet, tarayıcımı kullan"
DETECTED_YES_DESC = "Enabled by default açılır ve bu oturum bağlanır"
DETECTED_NO = "Hayır, tarayıcı araçları kapalı kalsın"
DETECTED_NO_DESC = "Enabled by default kapanır; Fusion Chrome kurulumunu önermeyi bırakır"

INSTALL_TITLE = "Fusion tarayıcını kullanmak istiyor"
INSTALL_YES = "Install extension"
INSTALL_YES_DESC = "Eklenti kurulumunu açar; kurulunca bu oturumda tarayıcı araçları çalışır"
INSTALL_LATER = "Not now"
INSTALL_LATER_DESC = "Görev tarayıcı araçları olmadan sürer; sonraki oturumda yeniden sorulabilir"
INSTALL_NEVER = "Don't ask again"
INSTALL_NEVER_DESC = "Sonraki oturumlarda sorulmaz; kurulumu istediğin an /chrome install ile yap"
INSTALL_DECLINED = (
    "Fusion Browser eklentisi kurulu değil ve kurulum bu oturumda ertelendi; tarayıcı araçları "
    "olmadan devam et. Kullanıcı kurulumu /chrome install ile yapabilir."
)

STATUS_TITLE = "Chrome'da Fusion (Fusion Browser)"
STATUS_LINE = "Status: {status}"
STATUS_ENABLED = "Enabled"
STATUS_DISABLED = "Disabled"
STATUS_NOT_CONNECTED = "Not connected"
EXTENSION_LINE = "Extension: {extension}"
EXTENSION_INSTALLED = "Installed"
EXTENSION_MISSING = "Not detected"
BROWSER_LINE = "Browser: {browser}"
BROWSER_WAITING = "eklentinin eşleşmesi bekleniyor"
BROWSER_CONNECTED = "bağlı"
DEFAULT_LINE = "Enabled by default: {value}"
DEFAULT_ON = "açık"
DEFAULT_OFF = "kapalı"
STATUS_OPTIONS = (
    "Seçenekler: /chrome reconnect (Reconnect extension) · /chrome select (Select browser…) · "
    "/chrome default on|off (Enabled by default) · /chrome install · /chrome permissions"
)
STATUS_OFF_HINT = (
    "Bu oturumda Chrome kapalı. Açmak için Fusion'ı --chrome ile başlat ya da "
    "/chrome default on ile sonraki oturumlarda varsayılan yap."
)

RECONNECTED = "Chrome bağlantısı yeniden başlatıldı; eklenti birkaç saniye içinde yeniden eşleşir."
SELECT_NONE = (
    "Bağlı tarayıcı yok; tarayıcıda Fusion Browser eklentisini açıp /chrome reconnect çalıştır."
)
SELECT_LIST_TITLE = "Bağlı tarayıcılar (seçmek için /chrome select <numara|deviceId>):"
SELECT_ITEM = "  {index}. {name} ({device}){mark}"
SELECT_IN_USE = " · kullanılıyor"
SELECT_DONE = "{name} ({device}) seçildi; başka tarayıcı bağlansa da bu seçim korunur."
SELECT_UNKNOWN = "Bağlı tarayıcılarda yok: {argument}."
SELECT_OFF = "Bu oturumda Chrome kapalı; önce --chrome ile başlat."
BROWSER_SELECTED = "Selected browser: {name} ({device})"
DEFAULT_SET_ON = "Enabled by default açıldı; sonraki oturumlar Chrome'a bağlanarak başlar."
DEFAULT_SET_OFF = "Enabled by default kapandı; Chrome yalnız --chrome ile açılır."
DEFAULT_USAGE = "Kullanım: /chrome default on|off"
PERMISSIONS_HINT = (
    "Site izinleri tarayıcı eyleminin onay kartında verilir: yalnız bu eylem, "
    "bu oturum boyunca bu siteye izin ver veya reddet. Yetişkin ve korsan "
    "içerik siteleri engellidir; finansal sitelerde izin her kipte sorulur. Kalıcı kurallar "
    "için /permissions; Chrome'un site erişimi Fusion Browser panelinde."
)
SITES_TITLE = "Your approved sites (bu oturum):"
SITES_USAGE = "Geri almak için: /chrome permissions revoke <site>"
SITES_EMPTY = "Bu oturumda verilmiş site yok."
SITES_REVOKED = "{host} site izni geri alındı; sonraki eylemde yeniden sorulur."
SITES_UNKNOWN = "{host} için bu oturumda verilmiş site izni yok."

INSTALL_STARTED = "Fusion Browser eklenti kurulumu başlatıldı: {detail}"
INSTALL_FAILED = "Eklenti kurulumu başlatılamadı: {error}"
UNKNOWN = "Bilinmeyen /chrome seçeneği: {argument}. " + STATUS_OPTIONS
DESKTOP_ONLY_CLI = "/chrome terminal oturumunda çalışır; masaüstünde Ayarlar › Tarayıcı'yı kullan."
SAVE_FAILED = "Chrome tercihi kaydedilemedi: {error}"

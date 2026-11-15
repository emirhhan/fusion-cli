"""`fusion mcp …` Claude Code paritesi metinleri (Türkçe; komut adları aynen)."""

from __future__ import annotations

SCOPE_LABELS = {
    "local": "yerel",
    "user": "kullanıcı",
    "project": "proje",
    "plugin": "eklenti",
    "managed": "yönetilen",
}
MANAGED_TRUST = (
    "'{name}' kuruluşunuzun yönettiği bir MCP sunucusu; güven kararı kullanıcı dosyasına "
    "yazılmaz, her araç çağrısı izin kurallarına göre sorulur."
)
#: REPL `/mcp` grup başlıkları; Claude Code `/mcp` grup adları aynen (#274).
SCOPE_GROUPS = (
    ("local", "Local MCPs (yalnız bu projede, size özel)"),
    ("project", "Project MCPs (.mcp.json, paylaşılan)"),
    ("user", "User MCPs (bütün projelerinizde)"),
    ("plugin", "Plugin MCPs (etkin eklentilerden)"),
    ("managed", "Managed MCPs (kuruluşunuzun yönettiği; düzenlenemez, kaldırılamaz)"),
)
LOCAL_ADDED = "'{name}' MCP sunucusu yalnız bu projeye (yerel kapsam) eklendi."
LOCAL_REMOVED = "'{name}' MCP sunucusu yerel kapsamdan kaldırıldı."
INVALID_NAME = (
    "Geçersiz sunucu adı: {name!r}. `fusion mcp` komutlarıyla eklenen adlar yalnız harf, "
    "rakam, - ve _ içerebilir."
)
BAD_HEADER = 'Geçersiz başlık: {raw!r}. Biçim: --header "Ad: değer"'
WS_NOT_FOR_ADD = (
    "`--transport` ws kabul etmez; WebSocket sunucusunu `fusion mcp add-json` ya da .mcp.json "
    "ile ekle."
)
DEPRECATED_URL = "Uyarı: --url kullanımdan kalkıyor; adresi ikinci argüman olarak ver: {hint}"
DEPRECATED_TOKEN_ENV = (
    "Uyarı: --token-env kullanımdan kalkıyor; Claude Code biçimi: "
    '--header "Authorization: Bearer ${{{name}}}"'
)
DEPRECATED_ENV_NAME = (
    "Uyarı: -e {name} (= olmadan) kullanımdan kalkıyor; Claude Code biçimi -e KEY=value. "
    "Şifreli depodaki değer için -e {name}=${{{name}}} yaz."
)
CLIENT_SECRET_PROMPT = "OAuth istemci sırrı"
CLIENT_SECRET_STORED = "İstemci sırrı sistem anahtarlığına kaydedildi (config'e yazılmadı)."
OAUTH_FLAGS_REMOTE_ONLY = "--client-id, --client-secret ve --callback-port yalnız http ve sse için."
AMBIGUOUS_SCOPE = "'{name}' birden çok kapsamda var ({scopes}); --scope ile hangisi olduğunu seç."
NOT_IN_SCOPE = "'{name}' {scope} kapsamında yok."
TOKENS_CLEARED = "Saklı OAuth kimlik bilgileri silindi."
LOGOUT_DONE = "'{name}' için saklı kimlik bilgileri silindi."
LOGOUT_NOT_REMOTE = "'{name}' uzak (http/sse) sunucu değil; silinecek kimlik bilgisi yok."
SKIPPED_ENTRY = "Atlandı: {problem}"
MISSING_VAR = "Uyarı: {name} için ortam değişkeni eksik: {names} (metin ${{…}} olarak kalır)"
STATUS_CONNECTED = "✔ Bağlandı"
STATUS_NEEDS_AUTH = "! Kimlik doğrulama gerekli"
STATUS_FAILED = "✘ Bağlanılamadı"
STATUS_PENDING = "⏸ Onay bekliyor"
STATUS_DISABLED = "○ Kapalı"
CHECKING_HEALTH = "MCP sunucularının durumu yoklanıyor…"
NO_BROWSER_PROMPT = (
    "Bu adresi tarayıcında aç, sonra adres çubuğundaki dönüş adresini buraya yapıştır"
)
NO_BROWSER_URL = "Yetkilendirme adresi:\n{url}"
DEPRECATED_BARE_MCP = (
    "Uyarı: alt komutsuz `fusion mcp` ile sunucu açmak kullanımdan kalkıyor; "
    "MCP istemcisi yapılandırmasında `fusion mcp serve` kullan."
)
PROJECT_CHOICES_RESET = (
    "Bu projedeki .mcp.json sunucuları için verilen bütün onay ve ret seçimleri sıfırlandı."
)
NO_PROJECT_CHOICES = "Bu projede sıfırlanacak .mcp.json onay seçimi yok."
APPROVAL_TITLE = "Yeni MCP sunucusu bulundu (.mcp.json): {name}"
APPROVAL_TARGET = "  {target}"
APPROVAL_NOTE = (
    "MCP sunucuları kod çalıştırabilir ya da dış hizmetlere erişebilir; yalnız güvendiğin "
    "sunucuları kullan."
)
APPROVAL_OPTIONS = (
    "  1. Bunu ve bu projedeki gelecek bütün MCP sunucularını kullan\n"
    "  2. Bu MCP sunucusunu kullan\n"
    "  3. Bu MCP sunucusunu kullanmadan devam et"
)
APPROVAL_ASK = "Seçim [1/2/3]"
TOOLS_USAGE = "Kullanım: /mcp tools <ad>"
TOOLS_NOT_CONNECTED = (
    "'{name}' henüz bağlanmadı; araçlar ilk bağlantıdan sonra görünür (/mcp reconnect {name})."
)
TOOLS_NONE = "'{name}' bağlı ama hiç araç sunmuyor."
TOOLS_HEADER = "{name} araçları ({count}):"
TOOL_NO_RULE = "kural yok (izin kipine göre sorulur)"
TOOL_COUNT = "{count} araç"

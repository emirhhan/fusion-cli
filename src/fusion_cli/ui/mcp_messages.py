"""`fusion mcp …` Claude Code paritesi metinleri (Türkçe; komut adları aynen)."""

from __future__ import annotations

SCOPE_LABELS = {
    "local": "yerel",
    "user": "kullanıcı",
    "project": "proje",
    "plugin": "eklenti",
}
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

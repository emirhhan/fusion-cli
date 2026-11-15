"""`/permissions` iletişim kutusu ve kip kapısının kullanıcıya görünen metinleri (#83, #85).

`ui/messages.py` zaten çok büyük; izin iletişim kutusunun metinleri burada toplanır.
"""

from __future__ import annotations

#: Ayar dosyası `disableAutoMode: "disable"` dediğinde (Claude #85).
AUTO_MODE_SETTING_DISABLED = "auto kipi ayarla kapatılmış (disableAutoMode)."

DIALOG_TITLE = "İzinler — sekme seç (Esc: kapat)"
TAB_ALLOW = "Allow"
TAB_ASK = "Ask"
TAB_DENY = "Deny"
TAB_WORKSPACE = "Workspace"
TAB_AUTO = "Auto mode"
TAB_ALLOW_DESC = "sormadan izin verilen araçlar"
TAB_ASK_DESC = "her zaman onay istenen araçlar"
TAB_DENY_DESC = "hiç kullanılamayan araçlar"
TAB_WORKSPACE_DESC = "Claude'un erişebildiği çalışma dizinleri"
TAB_AUTO_DESC = "auto kipi denetçisi ve son retleri"

RULES_TITLE = "{tab} kuralları — kural seç ya da yeni ekle (Esc: geri)"
ADD_RULE = "+ Yeni kural ekle…"
ADD_RULE_DESC = "ör. Bash(npm test *), Read(./.env), WebFetch(domain:example.com)"
RULE_PROMPT = "Kural kalıbını yaz (boş: vazgeç):"
#: Öneri varken boş giriş öneriyi kullanır (TUI'de Esc de boş giriştir); vazgeçmek için
#: sonraki kapsam seçiminde Esc.
RULE_PROMPT_SUGGESTED = (
    "Kural kalıbını yaz (boş: öneriyi kullan [{pattern}]; vazgeçmek için kapsam seçiminde Esc):"
)
SCOPE_TITLE = "Kural nereye kaydedilsin?"
SCOPE_LOCAL = "Proje ayarları (yerel)"
SCOPE_LOCAL_DESC = ".claude/settings.local.json — yalnız sen, bu proje"
SCOPE_PROJECT = "Proje ayarları"
SCOPE_PROJECT_DESC = ".claude/settings.json — depoyla paylaşılır"
SCOPE_USER = "Kullanıcı ayarları"
SCOPE_USER_DESC = "~/.claude/settings.json — tüm projeler"
RULE_ACTION_TITLE = "{rule} ({source})"
RULE_DELETE = "Kuralı sil"
RULE_BACK = "Geri"
RULE_READ_ONLY = "Bu kural salt okunur bir dosyada ({source}); dosyadan elle kaldır."

WORKSPACE_TITLE = "Çalışma dizinleri — dizin seç ya da ekle (Esc: geri)"
WORKSPACE_PRIMARY = "{path}"
WORKSPACE_PRIMARY_DESC = "birincil çalışma dizini"
WORKSPACE_EXTRA_DESC = "eklenen dizin (bu oturum)"
WORKSPACE_ADD = "+ Dizin ekle…"
WORKSPACE_ADD_DESC = "/add-dir ile aynı"
WORKSPACE_PROMPT = "Eklenecek dizinin yolu (boş: vazgeç):"
WORKSPACE_REMOVE = "Dizini kaldır"
WORKSPACE_PRIMARY_FIXED = "Birincil çalışma dizini kaldırılamaz; /cd ile taşı."

AUTO_TITLE = "Auto mode — son retler (Esc: geri)"
AUTO_NO_DENIALS = "Son auto mode reddi yok."
AUTO_STATUS = "Denetçi durumu"
AUTO_STATUS_DESC = "/auto-mode ile aynı özet"
AUTO_DENIAL_DESC = "auto mode reddetti"
AUTO_DENIAL_RULE = "Bu çağrıya izin veren kural ekle"
AUTO_DENIAL_RULE_DESC = "kalıp önerisi: {pattern}"
#: Özet joker (`*`, `?`) taşıyor ya da kısaltılmış: öneri istenenden geniş olurdu.
AUTO_DENIAL_RULE_NO_SUGGESTION = "öneri yok (özet joker ya da kısaltma içeriyor); kalıbı sen yaz"

DIALOG_CLOSED = "İzinler kapatıldı."

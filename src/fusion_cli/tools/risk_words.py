"""Riskli eylem sözcükleri: Chrome ve masaüstü aynı listeyle karar verir (P-008).

Eskiden liste `tools/chrome.py` içindeydi; masaüstü tıklaması (`desktop_mouse`) tıklanan
öğenin adına hiç bakmıyordu. Tek liste, iki yüzeyin ayrışmasını önler.
"""

from __future__ import annotations

import re

#: Tıklanınca geri dönüşü zor ya da dışa dönük iş yapan düğme adları (TR/EN).
#: Claude in Chrome da gezinmeyi ve sıradan tıklamayı sormaz; göndermede durur.
#:
#: Fiiller KELİME olarak aranır. Ölçüldü (27 Eylül): Instagram gönderi kartının
#: adı "1.234 beğenme, 12 yorum" içeriyor; alt dize araması bunu "beğen" sanıp
#: salt okuma turunu izin sorusunda durduruyordu.
RISKY_ACTION_PATTERN = re.compile(
    r"\b(?:gönder|paylaş|yayınla|yayımla|sil|silin|kaldır|satın al|ödeme yap|öde|"
    r"siparişi tamamla|siparişi onayla|onayla|kaydet|uygula|etkinleştir|devre dışı bırak|"
    r"duraklat|yorum yap|yanıtla|takip et|beğen|abone ol|kayıt ol|üye ol|hesap oluştur|"
    r"hesabı bağla|"
    # Ölçüldü (29 Ekim): aşağıdaki yaygın kalıcı düğmeler tanınmıyordu. Ekli Türkçe
    # biçimler ("Ödemeye geç") açıkça yazılır; sonek eşleme ("beğenme") 27 Eylül
    # hatasını geri getirirdi.
    r"siparişi ver|sipariş ver|ödemeye geç|ödemeyi tamamla|satın alın|bağış yap|"
    r"izin ver|yetki ver|yetkilendir|havale yap|para çek|teklif ver|yükselt|"
    r"aboneliği iptal et|siparişi iptal et|üyeliği iptal et|takibi bırak|"
    r"submit|send|post|publish|share|delete|remove|buy|purchase|pay|checkout|"
    r"confirm|save|apply|enable|disable|pause|follow|like|reply|comment|sign up|register|"
    r"create (?:an )?account|connect (?:your )?account|"
    r"place (?:an? |your |the |my )?(?:order|bid)|order now|join now|allow|authorize|approve|subscribe|donate|"
    r"withdraw|transfer|upgrade|unfollow|"
    r"cancel (?:my |your |the )?(?:subscription|order|membership|booking|reservation|plan))\b",
    re.IGNORECASE,
)

#: Bağlantı olsa bile oturumu kapatan tıklamalar sorulur.
LOGOUT_PATTERN = re.compile(r"çıkış yap|oturumu kapat|log ?out|sign ?out", re.IGNORECASE)

#: Masaüstüne özgü geri dönüşü zor menü/düğme adları (Finder, Posta): Chrome'da anlamsız.
DESKTOP_EXTRA_PATTERN = re.compile(
    r"\b(?:çöp sepetine taşı|çöp sepetini boşalt|çöpe at|kalıcı olarak sil|biçimlendir|"
    r"move to trash|empty trash|delete immediately|erase|format|force quit|zorla çık)\b",
    re.IGNORECASE,
)


def is_risky_label(label: str) -> bool:
    """Öğe adı gönder/sil/öde/çıkış türünden mi? (Chrome + masaüstü listeleri)."""
    return bool(
        RISKY_ACTION_PATTERN.search(label)
        or LOGOUT_PATTERN.search(label)
        or DESKTOP_EXTRA_PATTERN.search(label)
    )

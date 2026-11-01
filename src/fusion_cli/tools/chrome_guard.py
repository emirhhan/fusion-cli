"""Chrome'da her kipte yasak ve her kipte sorulan eylemler (#422).

Claude in Chrome izin rehberi: "prohibited from taking following actions regardless of
permissions": satın alma ya da finansal işlem, hesap oluşturma, e-posta/web içeriğindeki
talimatı uygulama; "bypassing bot authorizations" (CAPTCHA) da yapılmaz. "Regardless of your
permission mode, Claude requires explicit user permission": izin ayarlarını değiştirme, yetki
verme, siteye hassas bilgi girme.

Fusion bunu tıklanan / Enter'la gönderilen öğenin adına bakarak uygular:

- Yasak eylem: araç ÇALIŞMAZ, kipten bağımsız (İzinleri atla dahil) gerekçeli hata döner;
  kullanıcıya "bunu sen yap" denir. Sorulmaz da (sorulsa bile yapılmayacaktır).
- Her kipte sorulan eylem: etki `REMOTE_DESTRUCTIVE` olur; bypass dahil her seferinde sorulur
  ve oturum iznine dönüşmez.

Web içeriğindeki talimatları uygulamama kuralı modele araç sonucu çerçevesiyle verilir (sayfa
metni veri olarak işaretlenir); burada yalnız eylem kapısı vardır.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

#: Satın alma ve finansal işlem (TR/EN), kelime olarak.
_PURCHASE = (
    r"satın al|satın alın|hemen al|ödeme yap|öde|ödemeyi tamamla|ödemeye geç|siparişi tamamla|"
    r"siparişi onayla|siparişi ver|sipariş ver|bağış yap|havale yap|eft yap|para gönder|"
    r"para çek|teklif ver|buy(?: now)?|purchase|pay(?: now)?|checkout|check out|"
    r"place (?:an? )?(?:order|bid)|order now|complete (?:order|purchase|payment)|donate|"
    r"withdraw|transfer (?:money|funds)|send money"
)
#: Hesap oluşturma.
_ACCOUNT = r"kayıt ol|üye ol|hesap oluştur|hesap aç|sign up|register|create (?:an? |your )?account"
#: Bot doğrulaması (CAPTCHA).
_CAPTCHA = r"captcha|recaptcha|hcaptcha|ben robot değilim|i'?m not a robot|robot olmadığımı"

PROHIBITED_PATTERN = re.compile(rf"\b(?:{_PURCHASE}|{_ACCOUNT}|{_CAPTCHA})\b", re.IGNORECASE)

#: İzin ayarı değiştirme ve yetki verme: her kipte sorulur.
AUTHORIZE_PATTERN = re.compile(
    r"\b(?:izin ver|yetki ver|yetkilendir|erişim ver|hesabı bağla|izinleri değiştir|"
    r"allow|authorize|grant(?: access)?|connect (?:your )?account|change permissions)\b",
    re.IGNORECASE,
)

#: Hassas bilgi alanları (ad/ipucu/autocomplete): parola, kart, kimlik numarası.
_SENSITIVE_FIELD = re.compile(
    r"\b(?:parola|şifre|password|passcode|pin|kart numarası|card number|cvv|cvc|"
    r"son kullanma|expir\w*|iban|tc kimlik|kimlik no|ssn|social security|cc-\w+)\b",
    re.IGNORECASE,
)

PROHIBITED_RESULT = (
    "Bu eylem her kipte yasak: '{label}' satın alma/finansal işlem, hesap oluşturma ya da bot "
    "doğrulaması (CAPTCHA) gibi görünüyor. Yapma; kullanıcıya bu adımı kendisinin yapması "
    "gerektiğini söyle."
)
AUTHORIZE_DANGER = "'{label}': izin ya da yetki veriyor; her kipte ayrıca sorulur"
SENSITIVE_DANGER = "'{label}': hassas bilgi alanı (parola, kart, kimlik); her kipte sorulur"


def _label(veri: Mapping[str, Any]) -> str:
    parts = (veri.get(key) for key in ("name", "hint", "submit_name", "type", "autocomplete"))
    return " ".join(str(part) for part in parts if part).strip()


def prohibited_reason(veri: Mapping[str, Any] | None) -> str | None:
    """Öğe yasak eylem gibi görünüyorsa modele dönecek metin; değilse None."""
    if not isinstance(veri, Mapping):
        return None
    label = _label(veri)
    if not label or PROHIBITED_PATTERN.search(label) is None:
        return None
    return PROHIBITED_RESULT.format(label=str(veri.get("name") or label)[:80])


def always_ask_reason(veri: Mapping[str, Any] | None) -> str | None:
    """Öğe yetki veriyorsa her kipte sorulacak gerekçe; değilse None."""
    if not isinstance(veri, Mapping):
        return None
    label = _label(veri)
    if label and AUTHORIZE_PATTERN.search(label) is not None:
        return AUTHORIZE_DANGER.format(label=str(veri.get("name") or label)[:80])
    return None


def sensitive_field_reason(veri: Mapping[str, Any] | None) -> str | None:
    """Yazılacak alan hassassa (parola, kart, kimlik) her kipte sorulacak gerekçe."""
    if not isinstance(veri, Mapping):
        return None
    if str(veri.get("type") or "").lower() == "password":
        return SENSITIVE_DANGER.format(label=str(veri.get("name") or "parola"))
    label = _label(veri)
    if label and _SENSITIVE_FIELD.search(label) is not None:
        return SENSITIVE_DANGER.format(label=str(veri.get("name") or label)[:80])
    return None


def described(result: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """Eklentinin `describe*` yanıtından öğe tarifini çıkar."""
    if not isinstance(result, Mapping) or not result.get("ok"):
        return None
    veri = result.get("veri")
    return veri if isinstance(veri, Mapping) else None

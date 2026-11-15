"""Sesli turun bağlamını kullanıcı sözü ve kalıcı geçmişten ayrı tutar."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass

VOICE_RESPONSE_NOTE = (
    "Sesli konuşma: Türkçe, doğal ve doğrudan cevap ver. "
    "Kullanıcı ayrıntı istemedikçe bir veya iki kısa cümle kullan; önce doğrudan cevabı söyle. "
    "Araç, ajan, iç işlem veya model adlarını kullanıcı özellikle sormadıkça anlatma. "
    "Genel bilgi sorularını doğrudan yanıtla. Klasörleri veya dosyaları ancak kullanıcı isterse "
    "aç. "
    "Düşünme seslerini Talk verir. Cevaba hmm gibi yazılı bir dolgu ekleme."
)
#: Kesilen sözün prompta girecek üst sınırı (sınırsızdı, ölçüldü 30 Ekim).
MAX_INTERRUPTED_CHARS = 2_000
VOICE_METADATA_ERROR = "Sesli konuşma bağlamı geçersiz. Konuşmayı yeniden başlat."

_COURTESY = re.compile(r"^(?:tesekkur ederim|tesekkurler|sag ol|peki|bu arada) +")
_GEOGRAPHY = re.compile(
    r"(?:turkiye(?: ?nin)? baskenti (?:neresi|nerede|hangisi|ne)|"
    r"(?:turkiye(?: ?de)?|istanbul(?: ?da)?) kac (?:tane )?(?:cografi )?(?:bolge|sehir|il|ilce) "
    r"var)"
)


def is_voice_geography_question(text: str) -> bool:
    """Sık geçen, açık coğrafya sorularını çalışma alanı erişiminden ayır."""
    words = unicodedata.normalize("NFKD", text.lower().replace("ı", "i"))
    words = "".join(char for char in words if not unicodedata.combining(char))
    words = " ".join(re.sub(r"[^a-z ]", " ", words).split())
    return _GEOGRAPHY.fullmatch(_COURTESY.sub("", words)) is not None


@dataclass(frozen=True)
class VoiceTurnContext:
    """Yalnız ilgili model turunda kullanılan ses bilgisi."""

    interrupted: str = ""

    def prompt(self) -> str:
        """Kesilen sözün alıntı olduğunu belirtip yanıt yönergesine ekle."""
        if not self.interrupted:
            return VOICE_RESPONSE_NOTE
        quoted = json.dumps(self.interrupted, ensure_ascii=False)
        return (
            f"{VOICE_RESPONSE_NOTE}\nÖnceki yanıtın kesilen bölümü (alıntı): {quoted}. "
            "Son sözü bununla birlikte değerlendir; baştan tekrar etme."
        )


def parse_voice_context(value: object) -> VoiceTurnContext | None:
    """Tel alanını doğrula; yokluğu yazılı konuşma anlamına gelir."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"kesilen"}:
        raise ValueError(VOICE_METADATA_ERROR)
    interrupted = value.get("kesilen", "")
    if not isinstance(interrupted, str):
        raise ValueError(VOICE_METADATA_ERROR)
    return VoiceTurnContext(interrupted=interrupted[:MAX_INTERRUPTED_CHARS])

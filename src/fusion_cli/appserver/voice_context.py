"""Sesli turun bağlamını kullanıcı sözü ve kalıcı geçmişten ayrı tutar."""

from __future__ import annotations

import json
from dataclasses import dataclass

VOICE_RESPONSE_NOTE = (
    "Sesli konuşma: Türkçe, doğal ve doğrudan cevap ver. "
    "Kullanıcı ayrıntı istemedikçe kısa tut; önce sorusunu yanıtla."
)
VOICE_METADATA_ERROR = "Sesli konuşma bağlamı geçersiz. Konuşmayı yeniden başlat."


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
    return VoiceTurnContext(interrupted=interrupted)

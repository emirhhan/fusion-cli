"""Uzağa giden olay ve bildirimlerde sır/ortam bilgisi gizleme."""

from __future__ import annotations

import re
from typing import Any

from .constants import NOTIFICATION_SUMMARY_LIMIT

REDACTED = "[gizlendi]"

#: `anahtar = değer` atamasında değer YALNIZ sır gibi görünüyorsa gizlenir: en az 6 karakterlik
#: boşluksuz belirteç (ya da tırnaklı değer), ardından çağrı/indeks (`(`, `[`) OLMAYAN. Ölçüldü
#: (29 Ekim): eski desen `password = input()` gibi meşru kodu `[gizlendi]` yapıyordu (R1-05).
#: Anahtar adı `\b` ile biter: `max_tokens` eşleşmez, `OPENAI_API_KEY`/`access_token` eşleşir.
_ASSIGNMENT = re.compile(
    r"(?i)\b[A-Za-z0-9_]*(?:api[_-]?key|token|secret|password|parola)\b\s*[:=]\s*"
    r"(?:\"[^\"\n]{6,}\"|'[^'\n]{6,}'|[A-Za-z0-9_\-+/=.]{6,}(?![A-Za-z0-9_\-+/=.(\[]))"
)
_SECRET_PATTERNS = (
    re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\b[spr]k_(?:live|test)_[A-Za-z0-9]{10,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b"),  # Telegram bot belirteci
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/\-]{16,}=*"),
    _ASSIGNMENT,
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
#: Değeri tümden gizlenen JSON anahtarları: ad bu sözcüklerden biriyle BİTER. `max_tokens`
#: gibi yalnız "token" içeren anahtarların değeri sır değildir.
_SENSITIVE_KEY = re.compile(
    r"(?:^|[_\-.])(?:token|secret|password|parola|api[_-]?key|apikey|authorization)$",
    re.IGNORECASE,
)
#: Yarım kalmış sırrı bölmemek için bir sonraki parçaya bırakılan kuyruğun üst sınırı.
_DELTA_TAIL_LIMIT = 256


def redact_text(text: str) -> str:
    """Metindeki bilinen sır kalıplarını gizle."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return text


def redact_payload(value: Any) -> Any:  # noqa: ANN401 — JSON benzeri özyinelemeli veri
    """JSON benzeri veriyi kopyalayarak temizle; hassas anahtar değerleri gizlenir."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, dict):
        return {
            key: REDACTED
            if isinstance(key, str) and _SENSITIVE_KEY.search(key)
            else redact_payload(item)
            for key, item in value.items()
        }
    return value


def notification_summary(text: str) -> str:
    """Düşük hacimli bildirim özeti: gizlenmiş ve kısaltılmış, kod bloğu yok."""
    flat = " ".join(redact_text(text).split())
    if len(flat) <= NOTIFICATION_SUMMARY_LIMIT:
        return flat
    return flat[: NOTIFICATION_SUMMARY_LIMIT - 1] + "…"


def split_flushable(text: str) -> tuple[str, str]:
    """Akan metni (güvenle gönderilecek kısım, sonraki parçaya kalan kuyruk) diye ayır.

    Sır boşluksuz belirteçtir; son boşluk/satır sonuna kadar olan kısım güvenle gönderilir,
    yarım belirteç bir sonraki parçayla birleşip bütün hâlinde gizlenir. Boşluksuz çok
    uzun kuyruk (`_DELTA_TAIL_LIMIT`) beklemez. Delta'lar parça parça redakte edilince
    bölünmüş sır sızıyordu, final metin ise gizleniyordu (tutarsız, R1-05).
    """
    cut = max(text.rfind(" "), text.rfind("\n"), text.rfind("\t")) + 1
    if cut == 0:
        return (text, "") if len(text) > _DELTA_TAIL_LIMIT else ("", text)
    return text[:cut], text[cut:]

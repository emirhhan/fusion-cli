"""Uzağa giden olay ve bildirimlerde sır/ortam bilgisi gizleme."""

from __future__ import annotations

import re
from typing import Any

from .constants import NOTIFICATION_SUMMARY_LIMIT

REDACTED = "[gizlendi]"

_SECRET_PATTERNS = (
    re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b"),  # Telegram bot belirteci
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password|parola)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
_SENSITIVE_KEYS = ("token", "secret", "password", "parola", "api_key", "apikey", "authorization")


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
            if isinstance(key, str) and any(s in key.lower() for s in _SENSITIVE_KEYS)
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

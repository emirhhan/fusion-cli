"""Sır ve kişisel veri tespiti — tek merkezi desen listesi.

Öğrenilen dersler belleğe yazılmadan önce buradan geçer: bir sır ya da kişisel veri
içeren metin ASLA kalıcı belleğe girmez (RULES.md "Güvenlik", "Bellek ve Depolama").
Desenler tek yerde tanımlıdır ve testle kilitlenir; koda dağıtılmaz.

Amaç sıfır yanlış-negatif değil (bu imkânsız) — sık ve yüksek riskli biçimleri
(API anahtarı, token, özel anahtar, e-posta) yakalayıp belleği temiz tutmaktır.
"""

from __future__ import annotations

import re

#: Sır/kişisel veri işaret eden desenler. Sıra önemsizdir; ilk eşleşme yeter.
_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Bearer'ı generic Authorization alanından önce maskele; kısa test değerleri
    # de dahil olmak üzere değerin kendisi hiçbir ara aşamada görünür kalmasın.
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]+\b", re.IGNORECASE),
    re.compile(
        r'((?:["\']?)(?:auth|authorization|private[_-]key)(?:["\']?)\s*[:=]\s*["\']?)'
        r'([^"\'\s,}]+)(["\']?)',
        re.IGNORECASE,
    ),
    # Generic env/JSON auth keys, including vendor-prefixed names such as
    # ANTHROPIC_API_KEY and nested JSON config fields.
    re.compile(
        r'((?:["\']?)[A-Za-z0-9_.-]*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|'
        r'id[_-]?token|auth[_-]?token|client[_-]?secret|credential|token|secret|password)'
        r'[A-Za-z0-9_.-]*(?:["\']?)\s*[:=]\s*["\']?)([^"\'\s,}]+)(["\']?)',
        re.IGNORECASE,
    ),
    # Common JSON auth/config fields. Keep the key, replace only the value so
    # diagnostics remain useful without exposing bearer/access/refresh tokens.
    # OpenAI/benzeri anahtarlar: sk-... , anahtar önekleri
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\b(gh[pousr]|xox[baprs])-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS erişim anahtarı
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),  # Google API anahtarı
    # PEM özel anahtar başlığı
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # anahtar=değer biçiminde açıkça sır adı geçen atamalar
    re.compile(
        r"\b(api[_-]?key|secret|password|passwd|token|access[_-]?key|credential|auth|private)\b\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    # e-posta adresi (kişisel veri)
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
)


#: Sır/kişisel veri eşleşmelerinin yerine yazılan işaret.
REDACTED_MARK = "[gizlendi]"


def contains_sensitive(text: str) -> bool:
    """Metin bir sır ya da kişisel veri içeriyor mu."""

    return any(pattern.search(text) for pattern in _SENSITIVE_PATTERNS)


def redact(text: str) -> str:
    """Metindeki her sır/kişisel veri eşleşmesini `REDACTED_MARK` ile değiştir.

    `contains_sensitive` ile aynı desen listesini kullanır: log, trace ve JSONL
    çıktısı gibi sırların sızabileceği çıkış noktaları bu tek fonksiyondan geçer.
    """
    lowered = text.casefold()
    if not any(
        marker in lowered
        for marker in (
            "token", "secret", "password", "api", "bearer", "auth", "credential",
            "private", "sk-", "gh", "xox", "akia",
        )
    ):
        return text
    redacted = text
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(REDACTED_MARK, redacted)
    return redacted

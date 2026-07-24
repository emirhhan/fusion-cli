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
    # OpenAI/benzeri anahtarlar: sk-... , anahtar önekleri
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\b(gh[pousr]|xox[baprs])-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS erişim anahtarı
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),  # Google API anahtarı
    # PEM özel anahtar başlığı
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # Bearer token / Authorization
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{12,}\b", re.IGNORECASE),
    # anahtar=değer biçiminde açıkça sır adı geçen atamalar
    re.compile(
        r"\b(api[_-]?key|secret|password|passwd|token|access[_-]?key)\b\s*[:=]\s*\S{6,}",
        re.IGNORECASE,
    ),
    # e-posta adresi (kişisel veri)
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
)


def contains_sensitive(text: str) -> bool:
    """Metin bir sır ya da kişisel veri içeriyor mu."""

    return any(pattern.search(text) for pattern in _SENSITIVE_PATTERNS)

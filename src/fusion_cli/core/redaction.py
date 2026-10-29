"""Sır ve kişisel veri tespiti — tek merkezi desen listesi.

Öğrenilen dersler belleğe yazılmadan önce buradan geçer: bir sır ya da kişisel veri
içeren metin ASLA kalıcı belleğe girmez (RULES.md "Güvenlik", "Bellek ve Depolama").
Desenler tek yerde tanımlıdır ve testle kilitlenir; koda dağıtılmaz.

Ölçüldü (29 Ekim): `ghp_`/`gho_`/`github_pat_` belirteçleri, `Authorization: Basic`
değeri, `localhost`/IP/`ssh://` adreslerindeki URL parolası, boşluklu tırnaklı değerler
(`password: "iki kelime"`) ve imzalı adres sorgusu sızıyordu; `tests/test_diagnostic_redaction.py`
bunları sentetik fixture ile kilitler.

Amaç sıfır yanlış-negatif değil (bu imkânsız) — sık ve yüksek riskli biçimleri
(API anahtarı, token, özel anahtar, e-posta) yakalayıp belleği temiz tutmaktır.
"""

from __future__ import annotations

import re

#: Atamanın sağ tarafı: tırnaklı değer boşluk/virgül içerse de TAMAMEN sırdır.
#: Son kol, kapanmamış tırnakla başlayan değeri de (kesilmiş log) yakalar.
_VALUE = r"""(?:"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*'|["']?[^"'\s,}]+)"""

#: `şema://kullanıcı:parola@host` — parola sırdır; host ve yol tanı için kalır.
_URL_USERINFO = re.compile(r"\b([a-z][a-z0-9+.-]*://)[^\s/@:]*:[^\s/@]+@", re.IGNORECASE)
_URL_USERINFO_REPLACEMENT = r"\1[gizlendi]@"

#: Sır/kişisel veri işaret eden desenler. Sıra yalnız Basic/Bearer için önemli:
#: genel Authorization deseninden ÖNCE gelmeliler.
_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Tam veya kesilmiş PEM kaydının yalnız başlığı değil gövdesi de sırdır.
    re.compile(
        r"-----BEGIN ([A-Z0-9 ]*PRIVATE KEY)-----[\s\S]*?(?:-----END \1-----|\Z)",
        re.IGNORECASE,
    ),
    # Bearer'ı generic Authorization alanından önce maskele; kısa test değerleri
    # de dahil olmak üzere değerin kendisi hiçbir ara aşamada görünür kalmasın.
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]+\b", re.IGNORECASE),
    # Authorization: Basic <base64> — kimlik bilgisi şeması kelimesinden sonra gelir;
    # genel desen yalnız "Basic"i yakalayıp base64 kısmını açıkta bırakırdı.
    re.compile(
        r"\b(?:proxy-)?authorization\s*[:=]\s*[\"']?basic\s+[A-Za-z0-9+/_-]+=*",
        re.IGNORECASE,
    ),
    re.compile(
        r'((?:["\']?)(?:auth|authorization|private[_-]key)(?:["\']?)\s*[:=]\s*)' + _VALUE,
        re.IGNORECASE,
    ),
    # Generic env/JSON auth keys, including vendor-prefixed names such as
    # ANTHROPIC_API_KEY and nested JSON config fields.
    re.compile(
        r'((?:["\']?)[A-Za-z0-9_.-]*(?:api[_-]?key|access[_-]?token|refresh[_-]?token|'
        r"id[_-]?token|auth[_-]?token|client[_-]?secret|credential|token|secret|password)"
        r'[A-Za-z0-9_.-]*(?:["\']?)\s*[:=]\s*)' + _VALUE,
        re.IGNORECASE,
    ),
    # Common JSON auth/config fields. Keep the key, replace only the value so
    # diagnostics remain useful without exposing bearer/access/refresh tokens.
    # OpenAI/benzeri anahtarlar: sk-... , anahtar önekleri
    # OpenAI `sk-…` ve OpenRouter `sk-or-v1-…` (tire içerir); NVIDIA NIM `nvapi-…`.
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bnvapi-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b(gh[pousr]|xox[baprs])-[A-Za-z0-9_-]{10,}\b"),
    # GitHub: klasik `ghp_…` (alt çizgili) ve ince ayarlı `github_pat_…` belirteçleri.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS erişim anahtarı
    # İmzalı adreslerin sorgu sırları (önceden imzalı bulut bağlantıları).
    re.compile(r"(?<=[?&])(?:sig|signature|x-amz-signature|key|code)=[^&\s\"']+", re.IGNORECASE),
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

    return _URL_USERINFO.search(text) is not None or any(
        pattern.search(text) for pattern in _SENSITIVE_PATTERNS
    )


def redact(text: str) -> str:
    """Metindeki her sır/kişisel veri eşleşmesini `REDACTED_MARK` ile değiştir.

    `contains_sensitive` ile aynı desen listesini kullanır: log, trace ve JSONL
    çıktısı gibi sırların sızabileceği çıkış noktaları bu tek fonksiyondan geçer.
    """
    lowered = text.casefold()
    if not any(
        marker in lowered
        for marker in (
            "token",
            "secret",
            "password",
            "passwd",
            "access",
            "api",
            "bearer",
            "auth",
            "credential",
            "private",
            "sk-",
            "gh",
            "xox",
            "akia",
            "aiza",
            "@",
            "sig",
            "key",
            "github",
        )
    ):
        return text
    # URL kullanıcı bilgisi önce: sonra e-posta deseni "parola@host"u yutup host'u silerdi.
    redacted = _URL_USERINFO.sub(_URL_USERINFO_REPLACEMENT, text)
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(REDACTED_MARK, redacted)
    return redacted

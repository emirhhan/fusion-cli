"""Sır ve kişisel veri tespiti — tek merkezi desen listesi.

Öğrenilen dersler belleğe yazılmadan önce buradan geçer: bir sır ya da kişisel veri
içeren metin ASLA kalıcı belleğe girmez (RULES.md "Güvenlik", "Bellek ve Depolama").
Desenler tek yerde tanımlıdır ve testle kilitlenir; koda dağıtılmaz.

Ölçüldü (29 Ekim): `ghp_`/`gho_`/`github_pat_` belirteçleri, `Authorization: Basic`
değeri, `localhost`/IP/`ssh://` adreslerindeki URL parolası, boşluklu tırnaklı değerler
(`password: "iki kelime"`) ve imzalı adres sorgusu sızıyordu; ayrıca `sk_live_`/`rk_test_`,
JWT (`eyJ….eyJ….imza`) ve base64 (`+/=`) içeren `Bearer` değeri maskelenmiyordu (C1-03);
`tests/test_diagnostic_redaction.py` bunları sentetik fixture ile kilitler.

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
    # Değer base64 de olabilir (`+`, `/`, `=` dolgusu): bunlar da değerin parçasıdır.
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", re.IGNORECASE),
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
    # ANTHROPIC_API_KEY and nested JSON config fields. Önek/sonek {0,64} ile SINIRLI: sınırsız
    # `*` uzun boşluksuz gövdede (base64, minify çıktı) karesel çalışıyordu (ölçüldü 30 Ekim:
    # 3 200 karakter 1,3 sn; 50 000 karakter dakikalar).
    re.compile(
        r'((?:["\']?)[A-Za-z0-9_.-]{0,64}(?:api[_-]?key|access[_-]?token|refresh[_-]?token|'
        r"id[_-]?token|auth[_-]?token|client[_-]?secret|credential|token|secret|password)"
        r'[A-Za-z0-9_.-]{0,64}(?:["\']?)\s*[:=]\s*)' + _VALUE,
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
    # Stripe vb. `sk_live_…`/`sk_test_…`/`rk_live_…`/`pk_…` (alt çizgili; `sk-` deseni görmez).
    re.compile(r"\b[spr]k_(?:live|test)_[A-Za-z0-9]{10,}"),
    # JWT: üç base64url parça, ilk ikisi `eyJ` ile başlar.
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]+"),
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
    # `Cookie:` / `Set-Cookie:` başlığının değeri oturum sırrıdır (P-023): içe aktarılan
    # çerez tarayıcıdan hata metnine ya da transkripte dönerse satırın tamamı gizlenir.
    # Gerçek başlık `ad=değer` taşır; `cookie: string` (tip bildirimi) ya da `cookie: ...`
    # düz metni başlık DEĞİLDİR. Ölçüldü (31 Ekim): geniş desen grep sonucundaki kaynak
    # satırlarını maskeliyor, `cookie:` geçen dersleri `learning.py`'de attırıyordu.
    re.compile(r"\b(?:set-)?cookie\s*:\s*[^\s=;]+=[^\r\n]+", re.IGNORECASE),
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
            "k_live_",
            "k_test_",
            "eyj",
            "gh",
            "xox",
            "akia",
            "aiza",
            "@",
            "sig",
            "key",
            "github",
            "cookie",
        )
    ):
        return text
    # URL kullanıcı bilgisi önce: sonra e-posta deseni "parola@host"u yutup host'u silerdi.
    redacted = _URL_USERINFO.sub(_URL_USERINFO_REPLACEMENT, text)
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(REDACTED_MARK, redacted)
    return redacted


#: Akış gizleyicisinin bir satır tamamlanmadan tutabileceği en çok karakter. Çok uzun
#: satır (ör. minify edilmiş çıktı) sonsuza dek tutulmasın; aşılınca son boşlukta kesilir.
STREAM_HOLD_LIMIT = 512
#: Kapanmamış PEM bloğu için tutma sınırı (tam özel anahtar birkaç KB'tır).
STREAM_PEM_HOLD_LIMIT = 16_384
_PEM_BEGIN = "-----BEGIN"
_PEM_END = "-----END"


class StreamRedactor:
    """Parça parça gelen metni `redact` ile maskeler; parça sınırına denk gelen sırrı da yakalar.

    Ölçüldü (29 Ekim): gateway akışlı yolda `redact` hiç uygulanmıyordu; her parçayı ayrı
    maskelemek de bölünmüş sırrı (`ghp_` | `abc…`) kaçırır. Bu sınıf son SATIR SONUNA kadar olan
    kısmı verir, yarım satırı bir sonraki parçayla birleştirmek için tutar (kapanmamış PEM
    bloğunu bitene dek). Sırlar boşluksuz belirteçlerdir; satır sınırı onları asla bölmez.
    `flush()` akış bitince kalanı verir.
    """

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, text: str) -> str:
        """Yeni parçayı ekle; maskelenmiş, güvenle gösterilebilir kısmı döndür."""
        self._pending += text
        cut = self._pending.rfind("\n") + 1
        pem = self._pending.rfind(_PEM_BEGIN)
        if pem != -1 and self._pending.find(_PEM_END, pem) == -1:
            # Kapanmamış PEM bloğu: bitene (ya da tutma sınırına) dek hiçbir şey çıkmaz.
            cut = min(cut, pem) if len(self._pending) - pem <= STREAM_PEM_HOLD_LIMIT else cut
        if cut == 0 and len(self._pending) > STREAM_HOLD_LIMIT:
            cut = max(self._pending.rfind(" "), self._pending.rfind("\t")) + 1
        if cut <= 0:
            return ""
        ready, self._pending = self._pending[:cut], self._pending[cut:]
        return redact(ready)

    def flush(self) -> str:
        """Akış bitti: tutulan kalanı maskeleyip ver."""
        ready, self._pending = self._pending, ""
        return redact(ready)


#: Tarayıcı sürücüsünün (Playwright) hata metnine eklediği ham günlüğün başlangıcı.
_DRIVER_LOG_MARKERS = ("Call log:", "Call log")

#: Kullanıcıya gösterilen tek satırlık hata özetinin üst sınırı.
BRIEF_ERROR_CHARS = 160


def strip_driver_log(text: str, *, limit: int = BRIEF_ERROR_CHARS) -> str:
    """Ham sürücü günlüğünü (Playwright "Call log") at; tek satırlık kısa özet bırak.

    Ölçüldü (30 Ekim): pasif model seçeneğine tıklama zaman aşımı, onlarca satırlık
    "Call log" + öğenin tüm HTML özniteliklerini ekrana basıyordu. Ayrıntı günlük
    dosyasına gider (çağıran tam metni orada tutar); ekrana yalnız ilk anlamlı satır.
    """
    cut = text
    for marker in _DRIVER_LOG_MARKERS:
        index = cut.find(marker)
        if index != -1:
            cut = cut[:index]
    flat = " ".join(cut.split()).rstrip(". ")
    if len(flat) > limit:
        flat = flat[: limit - 1].rstrip() + "…"
    return flat or " ".join(text.split())[:limit]

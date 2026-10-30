"""Çerez dışa aktarma dosyaları — Netscape `cookies.txt` ve JSON — için saf ayrıştırıcı.

Ajanın tarayıcısı (`browser_*`) her turda boş bir bağlamla açılır; kullanıcının
girişli oturumunu ona taşımanın tek yolu çerezlerini bir profile aktarmaktır
(P-023). Bu modül yalnız dosya biçimlerini çözer ve Playwright'ın `storage_state`
sözlüğünü üretir; diske yazma, şifreleme ve tarayıcı `config`/`tools` katmanındadır.

Ölçüldü (31 Ekim): `providers/web_browser.py::parse_cookie_header` yalnız tek bir
`Cookie:` başlık metnini çözüyordu; alan adı, yol, süre ve `HttpOnly` bilgisi
taşınmıyordu. Netscape/JSON dışa aktarmalar bu alanları taşır ve tarayıcıya tam
çerez olarak verilebilir.

Çerez DEĞERİ sırdır: bu modül değerleri hiçbir yerde loglamaz, `repr`'a koymaz ve
özetlerde yalnız ad/alan adı/sayı verir (`cookie_domains`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .errors import BrowserProfileError

#: Dosya ayrıştırma hatası: aynı kökten türer ki CLI sınırı tek tipte yakalasın.
CookieFileError = BrowserProfileError

#: Netscape biçiminde `HttpOnly` çerezler alan adının önüne bu önekle yazılır (curl, wget).
_NETSCAPE_HTTPONLY_PREFIX = "#HttpOnly_"
#: Netscape satırındaki alan sayısı: domain, flag, path, secure, expiry, name, value.
_NETSCAPE_FIELDS = 7
#: Oturum çerezi: Playwright `expires=-1` ister.
SESSION_EXPIRES = -1.0
#: Profil adı: yol kaçışı ve gizli dosya olamaz; kısa ve dosya adı güvenli.
_PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
#: Playwright'ın kabul ettiği `sameSite` değerleri ve dışa aktarma araçlarının yazdığı eş adlar.
_SAME_SITE_ALIASES = {
    "lax": "Lax",
    "strict": "Strict",
    "none": "None",
    "no_restriction": "None",
    "unspecified": "Lax",
}
_DEFAULT_SAME_SITE = "Lax"


@dataclass(frozen=True)
class Cookie:
    """Tek bir çerez; `value` sırdır ve özetlere çıkmaz."""

    name: str
    value: str
    domain: str
    path: str = "/"
    #: Unix saniyesi; oturum çerezi için `SESSION_EXPIRES` (-1).
    expires: float = SESSION_EXPIRES
    secure: bool = False
    http_only: bool = False
    same_site: str = _DEFAULT_SAME_SITE

    def __repr__(self) -> str:  # pragma: no cover - yalnız sızıntı koruması
        return f"Cookie(name={self.name!r}, domain={self.domain!r}, value='[gizlendi]')"


def validate_profile_name(raw: str) -> str:
    """Profil adını temizle ve doğrula; geçersizse anlaşılır hata ver."""
    name = raw.strip()
    if not _PROFILE_NAME.match(name):
        raise BrowserProfileError(
            "Profil adı harf/rakamla başlamalı; yalnız harf, rakam, '-', '_' ve '.' "
            "içerebilir (en çok 64 karakter)."
        )
    return name


def parse_cookie_file(text: str, *, filename: str = "") -> tuple[Cookie, ...]:
    """İçeriğe bakarak biçimi seç (uzantı yanıltabilir) ve çerezleri döndür.

    Boş ya da çerezsiz içerik hata verir: sessizce boş profil kaydetmek, kullanıcının
    "içe aktardım ama giriş yok" diye saatlerce aramasına yol açar.
    """
    stripped = text.strip()
    if not stripped:
        raise CookieFileError(f"Çerez dosyası boş: {filename or '(içerik)'}")
    cookies = (
        parse_json_cookies(stripped) if stripped[0] in "[{" else parse_netscape_cookies(stripped)
    )
    if not cookies:
        raise CookieFileError(
            f"Dosyada çerez bulunamadı: {filename or '(içerik)'}. Netscape cookies.txt "
            "ya da JSON (Cookie-Editor / Playwright storage_state) bekleniyor."
        )
    return cookies


def parse_netscape_cookies(text: str) -> tuple[Cookie, ...]:
    """Netscape `cookies.txt` satırlarını çöz; bozuk satır atlanır, `#HttpOnly_` tanınır."""
    cookies: list[Cookie] = []
    for line in text.splitlines():
        http_only = line.startswith(_NETSCAPE_HTTPONLY_PREFIX)
        row = line[len(_NETSCAPE_HTTPONLY_PREFIX) :] if http_only else line
        if not row.strip() or row.startswith("#"):
            continue
        parts = row.rstrip("\r\n").split("\t")
        if len(parts) < _NETSCAPE_FIELDS:
            continue
        domain, _flag, path, secure, expiry, name = (part.strip() for part in parts[:6])
        # Değer son alandır ve sekme içermez; '=' içerebilir, bu yüzden bölünmez.
        value = parts[6]
        if not name or not domain:
            continue
        cookies.append(
            Cookie(
                name=name,
                value=value,
                domain=domain,
                path=path or "/",
                expires=_expires_from(expiry),
                secure=secure.upper() == "TRUE",
                http_only=http_only,
            )
        )
    return tuple(cookies)


def parse_json_cookies(text: str) -> tuple[Cookie, ...]:
    """JSON listesi (Cookie-Editor, EditThisCookie) ya da Playwright `storage_state` çöz."""
    try:
        data = json.loads(text)
    except ValueError as error:
        raise CookieFileError(f"JSON çerez dosyası okunamadı: {error}") from error
    if isinstance(data, dict):
        data = data.get("cookies")
    if not isinstance(data, list):
        raise CookieFileError("JSON çerez dosyası bir liste ya da {'cookies': [...]} olmalı.")
    cookies: list[Cookie] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        domain = str(item.get("domain") or "").strip()
        if not name or not domain:
            continue
        cookies.append(
            Cookie(
                name=name,
                value=str(item.get("value") or ""),
                domain=domain,
                path=str(item.get("path") or "/"),
                expires=_json_expires(item),
                secure=bool(item.get("secure", False)),
                http_only=bool(item.get("httpOnly", item.get("http_only", False))),
                same_site=_same_site(item.get("sameSite", item.get("same_site"))),
            )
        )
    return tuple(cookies)


def to_storage_state(cookies: tuple[Cookie, ...]) -> dict[str, object]:
    """Playwright `browser.new_context(storage_state=...)` sözlüğü."""
    return {
        "cookies": [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expires": cookie.expires,
                "httpOnly": cookie.http_only,
                "secure": cookie.secure,
                "sameSite": cookie.same_site,
            }
            for cookie in cookies
        ],
        "origins": [],
    }


def cookies_from_storage_state(state: object) -> tuple[Cookie, ...]:
    """Tarayıcıdan geri okunan `storage_state` sözlüğünü çerezlere çevir."""
    if not isinstance(state, dict):
        return ()
    return parse_json_cookies(json.dumps({"cookies": state.get("cookies") or []}))


def normalize_domain(domain: str) -> str:
    """Baştaki noktayı at, küçük harfe çevir: `.Example.com` → `example.com`."""
    return domain.strip().lstrip(".").lower()


def cookie_domains(cookies: tuple[Cookie, ...]) -> tuple[str, ...]:
    """Çerezlerin alan adları — tekil, normalize, sıralı. Özetlerde yalnız bu gösterilir."""
    return tuple(sorted({normalize_domain(cookie.domain) for cookie in cookies}))


def domain_allowed(domain: str, allowed: tuple[str, ...]) -> bool:
    """`sub.example.com`, `example.com` izniyle kapsanır; `notexample.com` kapsanmaz."""
    host = normalize_domain(domain)
    return any(host == item or host.endswith("." + item) for item in map(normalize_domain, allowed))


def filter_by_domains(
    cookies: tuple[Cookie, ...], allowed: tuple[str, ...] | None
) -> tuple[Cookie, ...]:
    """Yalnız izinli alan adlarının çerezlerini bırak. `None` = süzme yok; `()` = hiçbiri."""
    if allowed is None:
        return cookies
    return tuple(cookie for cookie in cookies if domain_allowed(cookie.domain, allowed))


def _expires_from(raw: str) -> float:
    try:
        value = float(raw)
    except ValueError:
        return SESSION_EXPIRES
    return value if value > 0 else SESSION_EXPIRES


def _json_expires(item: dict[str, object]) -> float:
    if item.get("session") is True:
        return SESSION_EXPIRES
    for key in ("expires", "expirationDate", "expiry"):
        raw = item.get(key)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return float(raw) if raw > 0 else SESSION_EXPIRES
    return SESSION_EXPIRES


def _same_site(raw: object) -> str:
    if not isinstance(raw, str):
        return _DEFAULT_SAME_SITE
    return _SAME_SITE_ALIASES.get(raw.strip().lower(), _DEFAULT_SAME_SITE)

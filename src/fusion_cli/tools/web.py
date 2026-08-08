"""Web araçları: anahtarsız arama ve sayfa okuma.

Arama iki farklı DuckDuckGo ucuna karşı çalışır. Bunlar HTML kazıma uçlarıdır ve
sayfa yapıları haber vermeden değişir; tek uca bağlanmak aracı sessizce kullanılmaz
hale getirir. Birincil uç bozulursa ikincisi kurtarır.

Sayfa okuma HTML'i düz metne indirger: script/style atılır, blok etiketleri satır
sonuna çevrilir, HTML varlıkları çözülür. Model ham etiket kalabalığı okumaz.
"""

from __future__ import annotations

import html as html_module
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET
from collections.abc import Callable
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx

from ..core.constants import (
    CAPABILITY_WALL_PREFIX,
    MAX_OUTPUT_CHARS,
    MAX_WEB_REDIRECTS,
    MAX_WEB_RESULTS,
    WEB_TIMEOUT_S,
    truncate_notice,
)
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str

_USER_AGENT = "Mozilla/5.0 (fusion-cli)"

#: `web_fetch`'in izin verdiği tek şemalar. `file://`, `gopher://` vb. reddedilir.
_ALLOWED_SCHEMES = frozenset({"http", "https"})

_SCRIPT_BLOCK = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")
_LINE_BREAK = re.compile(r"(?is)<br\s*/?>")
_BLOCK_END = re.compile(r"(?is)</(p|div|li|h[1-6]|tr)>")
_ANY_TAG = re.compile(r"(?s)<[^>]+>")
_INLINE_SPACE = re.compile(r"[ \t]+")
_EXTRA_BLANK_LINES = re.compile(r"\n\s*\n\s*\n+")

_DDG_RESULT = re.compile(r'(?is)<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>')
_DDG_LITE_RESULT = re.compile(r'(?is)<a[^>]+href="([^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>')


def web_fetch(args: ToolArgs, context: ToolContext) -> ToolResult:
    url = _normalize_url(require_str(args, "url"))
    reason = url_block_reason(url)
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")

    try:
        content_type, body = _fetch_following_redirects(url)
    except httpx.HTTPError as exc:
        return ToolResult.failure(f"Sayfa çekilemedi ({type(exc).__name__}): {exc}")
    except _BlockedRedirectError as exc:
        return ToolResult.failure(f"Yönlendirme engellendi: {exc}")

    text = strip_html(body) if _looks_like_html(content_type, body) else body
    govde = truncate_notice(text, MAX_OUTPUT_CHARS, ne="sayfa metni") or "(boş içerik)"
    duvar = access_wall_notice(text)
    return ToolResult(f"{duvar}\n\n{govde}" if duvar else govde)


#: Erişim duvarı işaretleri. Sayfa 200 döner ve METİN gelir; ama gelen metin istenen
#: içerik değil, kapının kendisidir.
_ACCESS_WALL_MARKERS: tuple[str, ...] = (
    "this store is password protected",
    "store is password protected",
    "bu mağaza şifre korumalı",
    "enter store password",
    "please enable javascript",
    "enable javascript to continue",
    "checking your browser",
    "verify you are human",
    "i'm not a robot",
    "log in to continue",
    "sign in to continue",
    "oturum açın",
)


def access_wall_notice(text: str) -> str:
    """Sayfa bir şifre/oturum/bot duvarıysa AÇIK bir uyarı üret; değilse boş metin.

    Ölçülen gerçek zarar: şifre korumalı bir mağazanın adresi çekildiğinde istek 200
    dönüyor, araç `ok=True` veriyor ve modele "This store is password protected"
    metni asıl sayfa içeriğiymiş gibi gidiyordu. Model başarı sinyali aldığı için
    kısıtı fark etmiyor, istenen siteyi göremediğini SÖYLEMİYOR ve onun yerine
    uydurma/jenerik bir çıktı üretiyordu.

    Uyarı araç SONUCUNA konur: bu proje boyunca ölçülen davranış, modelin prompt
    kurallarını atlayıp araç sonucuna tepki verdiğidir.
    """
    dusuk = text[:4000].lower()
    if not any(isaret in dusuk for isaret in _ACCESS_WALL_MARKERS):
        return ""
    return (
        f"{CAPABILITY_WALL_PREFIX} bu adres istenen içeriği DEĞİL, bir şifre/oturum/bot "
        "doğrulama sayfasını döndürdü. Aşağıdaki metin kapının kendisidir, sayfanın "
        "içeriği değildir. web_fetch form dolduramaz, şifre giremez ve oturum açamaz; "
        "Fusion'da etkileşimli tarayıcı aracı YOKTUR. Bu içeriği varmış gibi kullanma "
        "ve yerine benzerini UYDURMA — kullanıcıya siteye erişemediğini ve neye "
        "ihtiyacın olduğunu (dışa aktarılmış dosyalar, ekran görüntüsü, açık bir URL) "
        "açıkça söyle."
    )


class _BlockedRedirectError(Exception):
    """Bir yönlendirme SSRF doğrulamasını geçemedi ya da zincir çok uzadı."""


def _fetch_following_redirects(url: str) -> tuple[str, str]:
    """Yönlendirmeleri ELLE, her adımı SSRF'e karşı doğrulayarak takip et.

    `httpx`'in kendi `follow_redirects`'i ara hedefleri denetlemez; dış bir URL
    302 ile localhost/metadata'ya yönlendirebilir. Bu yüzden her yönlendirme
    yeni bir doğrulamadan (`url_block_reason`) geçirilir.
    """
    current = url
    # follow_redirects=False: yönlendirmeyi httpx değil biz yönetiriz.
    with httpx.Client(follow_redirects=False, timeout=WEB_TIMEOUT_S) as client:
        for _ in range(MAX_WEB_REDIRECTS + 1):
            response = client.get(current, headers={"User-Agent": _USER_AGENT})
            if not response.is_redirect:
                response.raise_for_status()
                return response.headers.get("content-type", ""), response.text
            location = response.headers.get("location", "")
            current = urljoin(current, location)
            reason = url_block_reason(current)
            if reason is not None:
                raise _BlockedRedirectError(reason)
        raise _BlockedRedirectError(f"en fazla {MAX_WEB_REDIRECTS} yönlendirme aşıldı")


def web_search(args: ToolArgs, context: ToolContext) -> ToolResult:
    query = require_str(args, "query")
    failures: list[str] = []

    for endpoint in SEARCH_ENDPOINTS:
        try:
            results = endpoint(query)
        except httpx.HTTPError as exc:
            failures.append(f"{endpoint.__name__}: {type(exc).__name__}")
            continue
        if results:
            return ToolResult("\n".join(results))

    if failures:
        return ToolResult.failure(f"Arama başarısız (denenen: {'; '.join(failures)})")
    return ToolResult("(sonuç bulunamadı)")


# --------------------------------------------------------------------------- #
# HTML işleme — saf fonksiyonlar, doğrudan test edilir.
# --------------------------------------------------------------------------- #


def strip_html(html: str) -> str:
    """HTML'i okunabilir düz metne indirge."""
    text = _SCRIPT_BLOCK.sub(" ", html)
    text = _LINE_BREAK.sub("\n", text)
    text = _BLOCK_END.sub("\n", text)
    text = _ANY_TAG.sub(" ", text)
    text = html_module.unescape(text)
    text = _INLINE_SPACE.sub(" ", text)
    return _EXTRA_BLANK_LINES.sub("\n\n", text).strip()


def clean_result_url(href: str) -> str:
    """DuckDuckGo'nun yönlendirme sarmalını çöz, protokolsüz adresi tamamla."""
    if "uddg=" in href:
        target = parse_qs(urlparse(href).query).get("uddg")
        if target:
            return unquote(target[0])
    if href.startswith("//"):
        return f"https:{href}"
    return href


def parse_results(html: str, pattern: re.Pattern[str]) -> list[str]:
    """Sonuç sayfasından "• başlık\\n  url" satırları çıkar."""
    results: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(html):
        url = clean_result_url(match.group(1))
        title = strip_html(match.group(2))
        if not title or not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        results.append(f"• {title}\n  {url}")
        if len(results) >= MAX_WEB_RESULTS:
            break
    return results


def url_block_reason(url: str) -> str | None:
    """URL SSRF açısından güvenli mi? Engellenmeliyse Türkçe gerekçe, değilse None.

    Saf ve test edilebilir: yalnızca ad çözümlemesi (`socket.getaddrinfo`) dışa
    çıkar. Reddedilenler: http/https dışı şema, hostsuz adres, özel/loopback/
    link-local/multicast/rezerve IP aralıkları ve bunlara çözülen alan adları
    (DNS rebinding'e karşı çözülmüş IP denetlenir).
    """
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return f"yalnızca http/https desteklenir (verilen: {parsed.scheme or 'şema yok'})"
    host = parsed.hostname
    if not host:
        return "adreste host yok"
    try:
        infos = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return f"alan adı çözülemedi: {host}"
    for info in infos:
        address = str(info[4][0])
        if _is_blocked_ip(address):
            return f"özel/yerel ağ adresi ({address})"
    return None


def _is_blocked_ip(address: str) -> bool:
    """Bu IP özel/loopback/link-local/rezerve mi? (metadata IP'si dâhil)"""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True  # Çözülemeyen bir şeyi güvenli varsaymayız.
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local  # 169.254.0.0/16 — bulut metadata ucu buradadır
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _normalize_url(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


def _looks_like_html(content_type: str, body: str) -> bool:
    return "html" in content_type.lower() or "<html" in body[:2000].lower()


def _post_search(url: str, query: str, pattern: re.Pattern[str]) -> list[str]:
    with httpx.Client(follow_redirects=True, timeout=WEB_TIMEOUT_S) as client:
        response = client.post(url, data={"q": query}, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        return parse_results(response.text, pattern)


def parse_bing_rss(xml_text: str) -> list[str]:
    """Bing RSS XML'inden "• başlık\\n  url" satırları çıkar (saf; ağ yok).

    Geçersiz XML boş liste döndürür. Tekrar eden ve http olmayan bağlantılar atılır.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    results: list[str] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link.startswith("http") or link in seen:
            continue
        seen.add(link)
        results.append(f"• {title}\n  {link}")
        if len(results) >= MAX_WEB_RESULTS:
            break
    return results


def _search_bing_rss(query: str) -> list[str]:
    """Bing'in herkese açık RSS sonuç biçimini kazımasız bir yedek olarak ara.

    Uç yapılandırılmış XML döndürür; bu yüzden bir arama-sonucu HTML sınıf adına
    bağlı kalmaktan daha dayanıklıdır. Hatalar `web_search` tarafından ele alınır ve
    DuckDuckGo uçları sonrasında yine kullanılabilir kalır.
    """
    url = f"https://www.bing.com/search?format=rss&q={quote_plus(query)}"
    with httpx.Client(follow_redirects=True, timeout=WEB_TIMEOUT_S) as client:
        response = client.get(url, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
    return parse_bing_rss(response.text)


def _search_html(query: str) -> list[str]:
    return _post_search("https://html.duckduckgo.com/html/", query, _DDG_RESULT)


def _search_lite(query: str) -> list[str]:
    return _post_search("https://lite.duckduckgo.com/lite/", query, _DDG_LITE_RESULT)


#: Testlerin uç değiştirmeden kazıma mantığını sınayabilmesi için açık liste.
SEARCH_ENDPOINTS: tuple[Callable[[str], list[str]], ...] = (
    _search_bing_rss,
    _search_html,
    _search_lite,
)

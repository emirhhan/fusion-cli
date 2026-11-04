"""Web araçları: anahtarsız arama ve sayfa okuma.

Arama iki farklı DuckDuckGo ucuna karşı çalışır. Bunlar HTML kazıma uçlarıdır ve
sayfa yapıları haber vermeden değişir; tek uca bağlanmak aracı sessizce kullanılmaz
hale getirir. Birincil uç bozulursa ikincisi kurtarır.

Sayfa okuma HTML'i düz metne indirger: script/style atılır, blok etiketleri satır
sonuna çevrilir, HTML varlıkları çözülür. Model ham etiket kalabalığı okumaz.
"""

from __future__ import annotations

import html as html_module
import re
import socket
import xml.etree.ElementTree as ET
from collections.abc import Callable, Collection
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx

from ..core.clock import SystemClock
from ..core.constants import (
    CAPABILITY_WALL_PREFIX,
    MAX_OUTPUT_CHARS,
    MAX_WEB_REDIRECTS,
    MAX_WEB_RESULTS,
    UNREACHABLE_RESOURCE_PREFIX,
    WEB_TIMEOUT_S,
    truncate_notice,
)
from ..core.network_address import is_public_ip
from ..core.protocols import Clock
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .pinned_http import PinnedTransport
from .web_evidence import (
    CONTENT_SUMMARY_CHARS,
    DATE_UNKNOWN,
    PageDates,
    SearchEntries,
    search_date_filter,
    timestamp,
)

_USER_AGENT = "Mozilla/5.0 (fusion-cli)"

#: `web_fetch` gövde üst sınırı (bayt). Sınırsız `client.get` çok büyük dosya/akış
#: adreslerinde bellek ve süre tüketirdi (ölçüldü, 30 Ekim); metin zaten
#: `MAX_OUTPUT_CHARS`'a kırpılıyor, 5 MiB sayfa metni için fazlasıyla yeter.
MAX_FETCH_BYTES = 5 * 1024 * 1024

#: Metne çevrilemeyen içerik türleri: çöp metin yerine açık hata (`download_file` yolu).
_BINARY_TYPE_PREFIXES = ("image/", "audio/", "video/", "font/")
_BINARY_TYPES = frozenset(
    {"application/pdf", "application/zip", "application/octet-stream", "application/gzip"}
)


def _is_binary_type(content_type: str) -> bool:
    kind = content_type.split(";", 1)[0].strip().lower()
    return kind.startswith(_BINARY_TYPE_PREFIXES) or kind in _BINARY_TYPES


#: `web_fetch`'in izin verdiği tek şemalar. `file://`, `gopher://` vb. reddedilir.
_ALLOWED_SCHEMES = frozenset({"http", "https"})

_SCRIPT_BLOCK = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")
_LINE_BREAK = re.compile(r"(?is)<br\s*/?>")
_BLOCK_END = re.compile(r"(?is)</(p|div|li|h[1-6]|tr)>")
_ANY_TAG = re.compile(r"(?s)<[^>]+>")
_INLINE_SPACE = re.compile(r"[ \t]+")
_EXTRA_BLANK_LINES = re.compile(r"\n\s*\n\s*\n+")

_DDG_RESULT = re.compile(r'(?is)<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>')


def web_fetch(args: ToolArgs, context: ToolContext, *, clock: Clock | None = None) -> ToolResult:
    url = _normalize_url(require_str(args, "url"))
    reason = url_block_reason(url)
    if reason is not None:
        return ToolResult.failure(_unreachable(reason))

    try:
        content_type, body, final_url = fetch_following_redirects(url)
    except httpx.HTTPError as exc:
        return ToolResult.failure(_unreachable(f"{type(exc).__name__}: {exc}"))
    except BlockedRedirectError as exc:
        return ToolResult.failure(f"Yönlendirme engellendi: {exc}")

    if _is_binary_type(content_type):
        return ToolResult.failure(
            f"{content_type.split(';', 1)[0]} ikili içerik, metne çevrilemez: {final_url}. "
            "Dosyayı projeye indirmek için download_file kullan (PDF/ZIP için sonra "
            "extract_archive ya da uygun araç)."
        )
    text = page_text(body, final_url) if _looks_like_html(content_type, body) else body
    govde = truncate_notice(text, MAX_OUTPUT_CHARS, ne="sayfa metni") or "(boş içerik)"
    duvar = access_wall_notice(text)
    fetched_at = timestamp(clock or SystemClock())
    dates = PageDates()
    if _looks_like_html(content_type, body):
        dates.feed(body)
    source = {
        "url": url,
        "final_url": final_url,
        "fetched_at": fetched_at,
        "published_at": dates.published_at,
        "updated_at": dates.updated_at,
        "date_evidence": "page_metadata" if dates.published_at or dates.updated_at else "unknown",
        "content_summary": text[:CONTENT_SUMMARY_CHARS],
    }
    provenance = f"Kaynak: {final_url}\nİstenen URL: {url}\nErişim zamanı: {fetched_at}"
    output = f"{provenance}\n\n{govde}"
    if duvar:
        # Kısıt öneki başarı kararının protokolüdür; provenance bunun önüne geçemez.
        output = f"{duvar}\n\n{output}"
    return ToolResult(output, structured={"source": source})


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
)

#: Sıradan sayfaların üst bilgisinde/menüsünde de geçen ifadeler ("Oturum açın / Üye ol").
#: Yalnız görünür metin KISA ise (gerçek bir giriş duvarı) duvar sayılır; uzun bir
#: e-ticaret sayfasında model gereksiz tarayıcı akışına sokulurdu (ölçüldü, 30 Ekim).
_WEAK_WALL_MARKERS: tuple[str, ...] = (
    "log in to continue",
    "sign in to continue",
    "oturum açın",
    "giriş yapın",
)
_WEAK_WALL_MAX_CHARS = 1_500


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
    guclu = any(isaret in dusuk for isaret in _ACCESS_WALL_MARKERS)
    zayif = len(text.strip()) < _WEAK_WALL_MAX_CHARS and any(
        isaret in dusuk for isaret in _WEAK_WALL_MARKERS
    )
    if not (guclu or zayif):
        return ""
    return (
        f"{CAPABILITY_WALL_PREFIX} bu adres istenen içeriği DEĞİL, bir şifre/oturum/bot "
        "doğrulama sayfasını döndürdü. Aşağıdaki metin kapının kendisidir, sayfanın "
        "içeriği değildir. web_fetch form dolduramaz ve oturum açamaz. ŞİMDİ NE YAP: "
        "kapıyı browser_open ile aç, browser_read ile alanın seçicisini gör, "
        "browser_type ile şifreyi/bilgiyi gir (submit: true) ve açılan sayfayı oku. "
        "Kapıyı geçemiyorsan (bilgi sende yok, doğrulama insan istiyor) bu içeriği "
        "varmış gibi kullanma ve yerine benzerini UYDURMA — kullanıcıya erişemediğini "
        "ve neye ihtiyacın olduğunu açıkça söyle."
    )


def _unreachable(reason: str) -> str:
    """Ulaşılamayan kaynağı, modelin UYDURMAYA itilmeyeceği biçimde bildir."""
    return (
        f"{UNREACHABLE_RESOURCE_PREFIX} bu adrese erişilemez ({reason}). İçerik "
        "ALINAMADI. Yerine benzerini UYDURMA ve alınmış gibi kullanma; kullanıcıya "
        "erişemediğini ve sebebini açıkça söyle."
    )


class BlockedRedirectError(Exception):
    """Bir yönlendirme SSRF doğrulamasını geçemedi ya da zincir çok uzadı."""


def fetch_following_redirects(url: str) -> tuple[str, str, str]:
    """Yönlendirmeleri ELLE, her adımı SSRF'e karşı doğrulayarak takip et.

    `httpx`'in kendi `follow_redirects`'i ara hedefleri denetlemez; dış bir URL
    302 ile localhost/metadata'ya yönlendirebilir. Bu yüzden her yönlendirme
    yeni bir doğrulamadan (`url_block_reason`) geçirilir.
    """
    current = url
    # follow_redirects=False: yönlendirmeyi httpx değil biz yönetiriz. Taşıma
    # denetlenen IP'ye bağlanır (DNS rebinding; bkz. `pinned_http`).
    with httpx.Client(
        follow_redirects=False, timeout=WEB_TIMEOUT_S, transport=PinnedTransport()
    ) as client:
        for _ in range(MAX_WEB_REDIRECTS + 1):
            with client.stream("GET", current, headers={"User-Agent": _USER_AGENT}) as response:
                if not response.is_redirect:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if _is_binary_type(content_type):
                        # Gövde HİÇ okunmaz: ikili içerik metne çevrilmeyecek.
                        return content_type, "", str(response.url)
                    return content_type, _read_capped(response), str(response.url)
                location = response.headers.get("location", "")
            current = urljoin(current, location)
            reason = url_block_reason(current)
            if reason is not None:
                raise BlockedRedirectError(reason)
        raise BlockedRedirectError(f"en fazla {MAX_WEB_REDIRECTS} yönlendirme aşıldı")


def _read_capped(response: httpx.Response) -> str:
    """Gövdeyi `MAX_FETCH_BYTES` ile sınırlı oku ve yanıtın kodlamasıyla çöz."""
    parts: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        parts.append(chunk[: MAX_FETCH_BYTES - total])
        total += len(chunk)
        if total >= MAX_FETCH_BYTES:
            break
    return b"".join(parts).decode(response.encoding or "utf-8", errors="replace")


def web_search(args: ToolArgs, context: ToolContext, *, clock: Clock | None = None) -> ToolResult:
    query = require_str(args, "query")
    searched_at = timestamp(clock or SystemClock())
    try:
        date_filter = search_date_filter(args, searched_at)
    except ValueError as error:
        return ToolResult.failure(str(error))
    failures: list[str] = []

    for endpoint in SEARCH_ENDPOINTS:
        try:
            results = endpoint(query, date_filter) if date_filter else endpoint(query)
        except httpx.HTTPError as exc:
            failures.append(f"{endpoint.__name__}: {type(exc).__name__}")
            continue
        if results:
            metadata = {
                "query": query,
                "searched_at": searched_at,
                "date_filter": date_filter,
                "date_filter_status": "requested" if date_filter else "not_requested",
            }
            heading = f"Arama zamanı: {searched_at}\n{DATE_UNKNOWN}"
            if date_filter:
                heading += f"\nİstenen tarih filtresi: {date_filter} (sağlayıcıya iletildi)"
            return ToolResult(f"{heading}\n\n" + "\n".join(results), structured=metadata)

    if failures:
        return ToolResult.failure(f"Arama başarısız (denenen: {'; '.join(failures)})")
    # Boş sonuç BAŞARI değildir: arama uçlarının biçimi bozulmuş olabilir. "Bulunamadı"
    # demek modelin "internette yok" sanmasına yol açıyordu (ölçüldü, 30 Ekim).
    return ToolResult.failure(
        "Arama uçları sonuç vermedi. Bu, konunun internette yok olduğu anlamına GELMEZ: "
        "sorguyu daha kısa/farklı sözcüklerle yeniden dene ya da web_fetch ile doğrudan "
        "bir kaynak adresini aç."
    )


# --------------------------------------------------------------------------- #
# HTML işleme — saf fonksiyonlar, doğrudan test edilir.
# --------------------------------------------------------------------------- #


class _PageLinks(HTMLParser):
    """Bağlantıları metinden ayır; yalnızca HTTP(S) hedeflerini koru."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag != "a" or not href or len(self.urls) >= 80:
            return
        url = urljoin(self.base_url, href)
        if urlparse(url).scheme in _ALLOWED_SCHEMES and url not in self.urls:
            self.urls.append(url)


def page_text(body: str, base_url: str) -> str:
    """Sayfa temizlenirken indirme bağlantıları kaybolup model URL uydurmasın."""
    links = _PageLinks(base_url)
    links.feed(body)
    text = strip_html(body)
    if not links.urls:
        return text
    # Bağlantılara ayrı yer ayır: uzun sayfa metni indirme hedeflerini kesmesin.
    body_budget = MAX_OUTPUT_CHARS // 2
    targets = truncate_notice("\n".join(links.urls), body_budget - 100, ne="bağlantılar")
    summary = truncate_notice(text, body_budget, ne="sayfa metni")
    return f"{summary}\n\nSayfadaki bağlantılar:\n{targets}"


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


def parse_anchor_results(html: str, css_class: str) -> list[str]:
    """Başlık/URL yanında varsa sağlayıcının snippet ve tarih beyanını koru."""
    parser = SearchEntries(css_class)
    parser.feed(html)
    results: list[str] = []
    seen: set[str] = set()
    for entry in parser.entries:
        url = clean_result_url(entry.href)
        title = strip_html(entry.title)
        if not title or not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        result = f"• {title}\n  {url}"
        if entry.published_at.strip():
            result += f"\n  Sağlayıcının tarih beyanı: {entry.published_at.strip()}"
        if entry.snippet.strip():
            result += f"\n  {entry.snippet.strip()}"
        results.append(result)
        if len(results) >= MAX_WEB_RESULTS:
            break
    return results


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


#: Kullanıcı mesajındaki yerel adresler: `localhost`, `127.0.0.1` ya da `[::1]` + port.
_LOOPBACK_URL = re.compile(r"https?://(localhost|127\.0\.0\.1|\[::1\]):(\d{2,5})\b", re.IGNORECASE)


def loopback_origins_in(text: str) -> set[str]:
    """Metinde açıkça yazılmış yerel adreslerin `host:port` kümesi."""
    return {f"{host.lower()}:{port}" for host, port in _LOOPBACK_URL.findall(text)}


def loopback_origin(url: str) -> str | None:
    """Adres yerel döngüdeyse `host:port` (genel ad; bkz. `_loopback_origin`)."""
    return _loopback_origin(url)


def _loopback_origin(url: str) -> str | None:
    """Adres yerel döngüdeyse `host:port`; değilse None.

    Ad çözümlemesine güvenmez: yalnız YAZILIŞI yerel olan adres sayılır, DNS ile
    127.0.0.1'e çözülen bir alan adı sayılmaz.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    if host not in ("localhost", "127.0.0.1", "::1") or port is None:
        return None
    return f"{'[::1]' if host == '::1' else host}:{port}"


def browser_block_reason(url: str, allowed_local: Collection[str] = ()) -> str | None:
    """Tarayıcı araçları için adres kapısı.

    `url_block_reason` ile aynıdır; tek fark, kullanıcının kendi mesajında yazdığı
    yerel adrese (`allowed_local`) izin vermesidir. Ölçüldü (4 Ekim kabul koşusu):
    yerel adres koşulsuz reddedilince model işi `curl` ile yaptı ve yerel sunucuyu
    internete açan bir tünel kurdu. Diğer özel ağ adresleri, bulut metadata ucu ve
    izin verilmemiş yerel portlar kapalı kalır.
    """
    origin = _loopback_origin(url)
    if origin is not None and origin in allowed_local:
        return None
    return url_block_reason(url)


def _is_blocked_ip(address: str) -> bool:
    """Bu IP genel internette değil mi? (metadata, CGNAT/Tailscale ve gömülü IPv4 dâhil)"""
    return not is_public_ip(address)


def _normalize_url(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


def _looks_like_html(content_type: str, body: str) -> bool:
    return "html" in content_type.lower() or "<html" in body[:2000].lower()


def _post_search(url: str, query: str, css_class: str, date_filter: str = "") -> list[str]:
    with httpx.Client(follow_redirects=True, timeout=WEB_TIMEOUT_S) as client:
        payload = {"q": query}
        if date_filter:
            payload["df"] = date_filter
        response = client.post(url, data=payload, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        return parse_anchor_results(response.text, css_class)


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
        result = f"• {title}\n  {link}"
        published = (item.findtext("pubDate") or "").strip()
        snippet = strip_html(item.findtext("description") or "")
        if published:
            result += f"\n  Sağlayıcının tarih beyanı: {published}"
        if snippet:
            result += f"\n  {snippet}"
        results.append(result)
        if len(results) >= MAX_WEB_RESULTS:
            break
    return results


def _relevant_to_query(results: list[str], query: str) -> list[str]:
    """Sorgudaki 3+ harfli sözcüklerden en az birini içermeyen sonuçları ele."""
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) >= 3]
    if not words:
        return results
    return [r for r in results if any(w in r.lower() for w in words)]


def _search_bing_rss(query: str, date_filter: str = "") -> list[str]:
    """Bing'in herkese açık RSS sonuç biçimini kazımasız bir yedek olarak ara.

    Uç yapılandırılmış XML döndürür; bu yüzden bir arama-sonucu HTML sınıf adına
    bağlı kalmaktan daha dayanıklıdır. Hatalar `web_search` tarafından ele alınır ve
    DuckDuckGo uçları sonrasında yine kullanılabilir kalır.
    """
    if date_filter:
        # RSS ucunda tarih filtresi doğrulanmadı; filtreyi sessizce düşürme.
        return []
    url = f"https://www.bing.com/search?format=rss&q={quote_plus(query)}"
    with httpx.Client(follow_redirects=True, timeout=WEB_TIMEOUT_S) as client:
        response = client.get(url, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
    # Ölçüldü (24 Ağustos canlı deneme): uç `q=`'yu yok sayıp konuma göre alakasız akış
    # döndürebiliyor. Sorgudan en az bir anlamlı sözcüğü başlıkta/adreste taşımayan sonuç atılır.
    return _relevant_to_query(parse_bing_rss(response.text), query)


def _search_html(query: str, date_filter: str = "") -> list[str]:
    return _post_search("https://html.duckduckgo.com/html/", query, "result__a", date_filter)


def _search_lite(query: str, date_filter: str = "") -> list[str]:
    return _post_search("https://lite.duckduckgo.com/lite/", query, "result-link", date_filter)


#: Testlerin uç değiştirmeden kazıma mantığını sınayabilmesi için açık liste.
#:
#: DuckDuckGo HTML önce dener: canlı denemede (2026-08-24) Bing'in `format=rss` ucu
#: `q=` parametresini artık yok sayıyor ve sorguyla hiç ilgisi olmayan, konuma göre
#: genel bir akış (ör. "Astana'da nereye gidilir") döndürüyordu. `web_search` boş
#: OLMAYAN ilk sonucu kabul ettiği için bu alakasız sonuçlar DDG'ye hiç düşmeden
#: kullanıcıya gidiyordu. Bing yapılandırılmış XML döndürdüğü için DDG çöktüğünde
#: son çare olarak tutulur, ama artık öncelik değildir.
SEARCH_ENDPOINTS: tuple[Callable[..., list[str]], ...] = (
    _search_html,
    _search_lite,
    _search_bing_rss,
)

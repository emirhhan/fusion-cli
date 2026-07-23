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
from collections.abc import Callable
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from ..core.constants import MAX_OUTPUT_CHARS, MAX_WEB_RESULTS, WEB_TIMEOUT_S
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str

_USER_AGENT = "Mozilla/5.0 (fusion-cli)"

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
    try:
        with httpx.Client(follow_redirects=True, timeout=WEB_TIMEOUT_S) as client:
            response = client.get(url, headers={"User-Agent": _USER_AGENT})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            body = response.text
    except httpx.HTTPError as exc:
        return ToolResult.failure(f"Sayfa çekilemedi ({type(exc).__name__}): {exc}")

    text = strip_html(body) if _looks_like_html(content_type, body) else body
    return ToolResult(text[:MAX_OUTPUT_CHARS] or "(boş içerik)")


def web_search(args: ToolArgs, context: ToolContext) -> ToolResult:
    query = require_str(args, "query")
    failures: list[str] = []

    for endpoint in (_search_html, _search_lite):
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


def _normalize_url(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


def _looks_like_html(content_type: str, body: str) -> bool:
    return "html" in content_type.lower() or "<html" in body[:2000].lower()


def _post_search(url: str, query: str, pattern: re.Pattern[str]) -> list[str]:
    with httpx.Client(follow_redirects=True, timeout=WEB_TIMEOUT_S) as client:
        response = client.post(url, data={"q": query}, headers={"User-Agent": _USER_AGENT})
        response.raise_for_status()
        return parse_results(response.text, pattern)


def _search_html(query: str) -> list[str]:
    return _post_search("https://html.duckduckgo.com/html/", query, _DDG_RESULT)


def _search_lite(query: str) -> list[str]:
    return _post_search("https://lite.duckduckgo.com/lite/", query, _DDG_LITE_RESULT)


#: Testlerin uç değiştirmeden kazıma mantığını sınayabilmesi için açık liste.
SEARCH_ENDPOINTS: tuple[Callable[[str], list[str]], ...] = (_search_html, _search_lite)

"""Site tarama — aynı alan adında sayfaları gez, yapıyı ve görselleri çıkar.

`web_fetch` tek sayfa okur; "şu siteyi incele, görsellerini al" isteğinde model
sayfaları elle tek tek çağırıyor ve çoğu kez ana sayfada kalıyordu. Bu araç:

- yalnız başlangıç adresinin alan adında kalır (dış bağlantı izlenmez),
- robots.txt'ye uyar (yasaklı yol ziyaret edilmez, `Crawl-delay` geçerlidir),
- istekler arasında bekler (`CRAWL_DELAY_S`), sınırlı sayfa/derinlik gezer,
- her adresi web aracıyla AYNI SSRF denetiminden geçirir (yönlendirmeler dâhil).

Çıktı salt okumadır: sayfa başlıkları, başlıklar, açıklama ve görsel listesi
(gerçek adres, alt metin, bildirilen ölçü). Görseli indirmek ayrı ve onaylı bir
iştir (`download_file`): başkasının görselinin kullanım hakkı olmayabilir.
"""

from __future__ import annotations

import time
import urllib.robotparser
from collections import deque
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from ..core.constants import CRAWL_DELAY_S, CRAWL_MAX_DEPTH, CRAWL_MAX_PAGES
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import require_str
from .web import BlockedRedirectError, fetch_following_redirects, url_block_reason

#: Kullanıcı sayfa/derinlik vermezse: bir sitenin vitrinini görmeye yeten küçük tarama.
DEFAULT_PAGES = 20
DEFAULT_DEPTH = 2
_USER_AGENT = "fusion-cli"
#: Gezilmeyecek dosya türleri (sayfa değil).
_SKIP_SUFFIXES = (
    ".pdf", ".zip", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg",
    ".mp4", ".mp3", ".css", ".js", ".xml", ".json", ".ico",
)  # fmt: skip


@dataclass
class PageInfo:
    url: str
    title: str = ""
    description: str = ""
    headings: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    images: list[tuple[str, str, str]] = field(default_factory=list)
    og_image: str = ""


class _PageParser(HTMLParser):
    """Sayfadan başlık, açıklama, h1-h2, bağlantı ve görselleri topla."""

    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.page = PageInfo(url=base)
        self._base = base
        self._capture: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag in ("title", "h1", "h2"):
            self._capture, self._buffer = tag, []
        elif tag == "a" and values.get("href"):
            self.page.links.append(urljoin(self._base, values["href"]))
        elif tag == "img":
            self._image(values)
        elif tag == "meta":
            self._meta(values)

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self._capture:
            return
        text = " ".join("".join(self._buffer).split())
        if tag == "title":
            self.page.title = text
        elif text:
            self.page.headings.append(f"{tag}: {text}")
        self._capture = None

    def _image(self, values: dict[str, str]) -> None:
        src = values.get("src") or values.get("data-src") or ""
        srcset = values.get("srcset") or values.get("data-srcset") or ""
        if srcset:
            # En geniş aday: srcset'in son öğesi genellikle en büyüğüdür.
            src = srcset.split(",")[-1].strip().split(" ")[0] or src
        if not src or src.startswith("data:"):
            return
        boyut = "×".join(v for v in (values.get("width", ""), values.get("height", "")) if v)
        self.page.images.append((urljoin(self._base, src), values.get("alt", ""), boyut))

    def _meta(self, values: dict[str, str]) -> None:
        name = (values.get("name") or values.get("property") or "").lower()
        if name == "description":
            self.page.description = values.get("content", "")
        elif name in ("og:image", "twitter:image") and not self.page.og_image:
            self.page.og_image = urljoin(self._base, values.get("content", ""))


def parse_page(url: str, html: str) -> PageInfo:
    parser = _PageParser(url)
    parser.feed(html)
    return parser.page


def site_crawl(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Başlangıç adresinden aynı alan adındaki sayfaları gez ve özetle."""
    start = _normalize(require_str(args, "url"))
    reason = url_block_reason(start)
    if reason is not None:
        return ToolResult.failure(f"Taranamaz: {reason}")
    max_pages = _bounded(args.get("max_pages"), DEFAULT_PAGES, CRAWL_MAX_PAGES)
    max_depth = _bounded(args.get("max_depth"), DEFAULT_DEPTH, CRAWL_MAX_DEPTH)
    robots = _robots(start)
    delay = max(CRAWL_DELAY_S, float(robots.crawl_delay(_USER_AGENT) or 0) if robots else 0.0)
    pages, skipped = _walk(start, max_pages, max_depth, robots, delay, context)
    if not pages:
        return ToolResult.failure("Hiç sayfa okunamadı. " + "; ".join(skipped[:3]))
    return ToolResult(_report(start, pages, skipped))


def _walk(
    start: str,
    max_pages: int,
    max_depth: int,
    robots: urllib.robotparser.RobotFileParser | None,
    delay: float,
    context: ToolContext,
) -> tuple[list[PageInfo], list[str]]:
    host = urlparse(start).netloc
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen = {start}
    pages: list[PageInfo] = []
    skipped: list[str] = []
    while queue and len(pages) < max_pages and not context.cancelled.is_set():
        url, depth = queue.popleft()
        if robots is not None and not robots.can_fetch(_USER_AGENT, url):
            skipped.append(f"robots.txt yasaklıyor: {url}")
            continue
        if pages:
            _sleep(delay)
        try:
            content_type, body, final_url = fetch_following_redirects(url)
        except (httpx.HTTPError, BlockedRedirectError) as error:
            skipped.append(f"{url}: {type(error).__name__}")
            continue
        if "html" not in content_type.lower():
            continue
        page = parse_page(final_url, body)
        pages.append(page)
        if depth >= max_depth:
            continue
        for link in page.links:
            clean = urldefrag(link)[0]
            if _same_site(clean, host) and clean not in seen and not _is_asset(clean):
                seen.add(clean)
                queue.append((clean, depth + 1))
    return pages, skipped


def _sleep(seconds: float) -> None:
    """Nazik tarama beklemesi (testler bu fonksiyonu sahtesiyle değiştirir)."""
    time.sleep(seconds)


def _robots(start: str) -> urllib.robotparser.RobotFileParser | None:
    """robots.txt'yi aynı SSRF denetimiyle oku; yoksa ya da okunamazsa kısıt yok."""
    parsed = urlparse(start)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        _content_type, body, _final = fetch_following_redirects(robots_url)
    except (httpx.HTTPError, BlockedRedirectError):
        return None
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(body.splitlines())
    return parser


def _report(start: str, pages: list[PageInfo], skipped: list[str]) -> str:
    lines = [f"Tarama: {start} — {len(pages)} sayfa okundu."]
    images: dict[str, tuple[str, str, str]] = {}
    for page in pages:
        lines.append(f"\n## {page.title or '(başlıksız)'}\n{page.url}")
        if page.description:
            lines.append(f"açıklama: {page.description[:200]}")
        lines.extend(page.headings[:8])
        for src, alt, size in page.images:
            images.setdefault(src, (alt, size, page.url))
        if page.og_image:
            images.setdefault(page.og_image, ("paylaşım görseli (og:image)", "", page.url))
    lines.append(f"\n## Görseller ({len(images)})")
    for src, (alt, size, where) in images.items():
        lines.append(f"- {src} | alt: {alt or '—'} | {size or 'ölçü yok'} | sayfa: {where}")
    if skipped:
        lines.append(f"\nAtlanan ({len(skipped)}): " + "; ".join(skipped[:10]))
    lines.append(
        "\nNot: Görseller başkasına ait olabilir; kullanmadan önce hakkını doğrula. "
        "İndirmek için download_file kullan."
    )
    # Uzun rapor kırpılmaz: kayıt defteri büyük çıktıyı diske alır ve modele yolunu verir.
    return "\n".join(lines)


def _normalize(url: str) -> str:
    url = url.strip()
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


def _same_site(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.netloc == host


def _is_asset(url: str) -> bool:
    return urlparse(url).path.lower().endswith(_SKIP_SUFFIXES)


def _bounded(value: object, default: int, ceiling: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return default
    return min(value, ceiling)

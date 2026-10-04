"""Çalışan sayfayı açıp ÖLÇ: gerçekten bir site mi, yoksa hata/boş sayfa mı?

`php -l` temiz geçen bir tema yine de açılmayabilir (eksik çekirdek, fatal error,
beyaz ekran). "Doğrulandı" demek için sayfanın kendisine bakmak gerekir.

Ölçülenler: HTTP durumu, başlık, görünür metin uzunluğu, PHP/WordPress hata metni,
konsol hataları ve ana sayfadaki birkaç iç bağlantının durumu. Playwright varsa
ekran görüntüsü de alınır (görebilen model sonucu GÖRÜR); yoksa düz HTTP ile ölçülür.
"""

from __future__ import annotations

import asyncio
import contextlib
import html
import http.client
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

#: Sayfanın yüklenmesi için tanınan süre (ilk WordPress isteği önbelleği ısıtır).
PROBE_TIMEOUT_S = 30.0
#: Ana sayfadan izlenecek en fazla iç bağlantı ("her sayfa çalışıyor mu" örneği).
MAX_LINKS = 6
#: Görünür metni bundan kısa sayfa "boş" sayılır (beyaz ekran, yalnız iskelet).
MIN_VISIBLE_CHARS = 40
#: Sorun listesinde adıyla gösterilecek en fazla yüklenemeyen kaynak (toplam sayı da yazılır).
MAX_FAILED_RESOURCES = 6
#: Ekran görüntüsü ölçüsü: masaüstü görünümü.
SCREENSHOT_WIDTH = 1280
SCREENSHOT_HEIGHT = 800

#: PHP ve WordPress'in sayfaya bastığı hata kalıpları.
_PAGE_ERRORS = re.compile(
    r"Fatal error|Parse error|Uncaught (?:Error|Exception)|<b>Warning</b>:|"
    r"There has been a critical error|Error establishing a database connection|"
    r"kritik bir hata|veritabanı bağlantısı kurulurken hata",
    re.IGNORECASE,
)

#: Bir hata satırından modele gidecek en fazla karakter (mesaj + dosya:satır).
MAX_ERROR_LINE = 300


def page_error_lines(body: str) -> tuple[str, ...]:
    """Sayfadaki PHP/WordPress hatalarını MESAJIYLA döndür (dosya ve satır dahil).

    Ölçüldü (3 Ekim 2026, 17. kabul koşusu): yalnız kalıbın kendisi ("Fatal error")
    bildiriliyordu; düzeltmeyi belirleyen "Class ... not found in header.php:42" modele
    hiç gitmedi.
    """
    text = html.unescape(re.sub(r"<[^>]+>", "", body))
    found: list[str] = []
    line_end = -1
    for match in _PAGE_ERRORS.finditer(text):
        if match.start() < line_end:
            continue  # aynı satırdaki ikinci kalıp ("Fatal error: Uncaught Error")
        newline = text.find("\n", match.start())
        line_end = newline if newline >= 0 else len(text)
        found.append(" ".join(text[match.start() : line_end].split())[:MAX_ERROR_LINE])
    return tuple(dict.fromkeys(found))


@dataclass(frozen=True, slots=True)
class LinkCheck:
    url: str
    status: int
    error: str = ""
    #: Sayfa ana sayfayla aynı metni gösteriyor (şablon eksik: istek ana sayfaya düşüyor).
    same_as_home: bool = False


@dataclass(frozen=True, slots=True)
class PageProbe:
    url: str
    status: int
    title: str
    visible_chars: int
    page_errors: tuple[str, ...]
    console_errors: tuple[str, ...] = ()
    links: tuple[LinkCheck, ...] = ()
    screenshot: bytes | None = None
    #: İstenmişse sayfada çalıştırılan ölçüm betiğinin sonucu (bkz. `design_compare`).
    measured: dict[str, Any] | None = None
    #: Sayfanın istediği ama yüklenemeyen kaynaklar: "HTTP 404 /yol/dosya.jpg".
    failed_resources: tuple[str, ...] = ()
    #: Sayfanın istek attığı dış alan adları (yazı tipi CDN'i, kaynak sitenin API'si…).
    external_hosts: tuple[str, ...] = ()

    @property
    def problems(self) -> tuple[str, ...]:
        """Sayfayı BOZUK sayan bulgular (boşsa sayfa çalışıyor)."""
        found: list[str] = []
        if self.status >= 400 or self.status == 0:
            found.append(f"ana sayfa HTTP {self.status or 'yanıt yok'} döndü")
        found.extend(f"sayfada hata: {error}" for error in self.page_errors)
        if not self.page_errors and self.status < 400 and self.visible_chars < MIN_VISIBLE_CHARS:
            found.append(f"sayfa neredeyse boş ({self.visible_chars} karakter görünür metin)")
        for link in self.links:
            if link.status >= 400 or link.status == 0 or link.error:
                ek = f", {link.error}" if link.error else ""
                found.append(f"bağlantı açılmıyor: {link.url} (HTTP {link.status}{ek})")
            elif link.same_as_home:
                # Ölçüldü (3 Ekim 2026, 14. kabul koşusu): temada `page.php` yoktu; sepet ve
                # ödeme sayfaları 200 dönüp ANA SAYFAYI gösterdi, araç "açıldı" dedi.
                found.append(
                    f"bağlantı ana sayfayla aynı içeriği gösteriyor: {link.url} (sayfa şablonu "
                    "eksik olabilir, ör. page.php)"
                )
        if self.failed_resources:
            # Ölçüldü (2 Ekim 2026, 8. kabul koşusu): tema 12 görsele bağlanıyordu ama
            # dosyalar hiç kopyalanmamıştı; kahraman alanı boş göründü, araç "sayfa hatasız
            # açıldı" dedi.
            shown = "; ".join(self.failed_resources[:MAX_FAILED_RESOURCES])
            found.append(
                f"{len(self.failed_resources)} kaynak yüklenemedi (dosya yok ya da yol yanlış): "
                f"{shown}"
            )
        return tuple(found)

    def summary(self) -> str:
        baslik = self.title or "-"
        sayfa = f"HTTP {self.status}, başlık '{baslik}', {self.visible_chars} karakter metin"
        acik = sum(1 for link in self.links if 0 < link.status < 400 and not link.error)
        if self.links:
            sayfa += f", {acik}/{len(self.links)} iç bağlantı açıldı"
        return sayfa


async def probe(
    url: str,
    *,
    browser: bool = True,
    measure_script: str | None = None,
    viewport: tuple[int, int] = (SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT),
) -> PageProbe:
    """Sayfayı ölç; `browser` ve Playwright varsa tarayıcıda (konsol + ekran görüntüsü).

    Doğrulama kapısı `browser=False` verir: her turda tarayıcı açmak turu yavaşlatır,
    HTTP + hata metni + bağlantılar "site çalışıyor mu" sorusuna yeter.

    `measure_script` verilirse aynı sayfa oturumunda çalıştırılır ve sonucu `measured`
    alanına konur (kaynak siteyle karşılaştırma için; ikinci bir tarayıcı açılmaz).
    """
    base = await asyncio.to_thread(_http_probe, url)
    links = await asyncio.to_thread(_check_links, url, base.links, base.text)
    seen = _BrowserResult()
    if browser:
        with contextlib.suppress(Exception):
            # Tarayıcı yoksa/açılamazsa ölçüm HTTP ile yetinir; önizleme düşmez.
            seen = await _browser_probe(url, measure_script, viewport)
    return PageProbe(
        url=url,
        status=base.status,
        title=base.title,
        visible_chars=base.visible_chars,
        page_errors=base.page_errors,
        console_errors=seen.console,
        links=links,
        screenshot=seen.screenshot,
        measured=seen.measured,
        failed_resources=seen.failed,
        external_hosts=seen.external_hosts,
    )


@dataclass(frozen=True, slots=True)
class _HttpResult:
    status: int
    title: str
    visible_chars: int
    page_errors: tuple[str, ...]
    links: tuple[str, ...]
    #: Görünür metin (ana sayfayla karşılaştırma için).
    text: str = ""


def _http_probe(url: str) -> _HttpResult:
    status, body = _fetch(url)
    parser = _PageText()
    with contextlib.suppress(Exception):
        parser.feed(body)
    errors = page_error_lines(body)
    host = urlparse(url).netloc
    links = tuple(
        dict.fromkeys(
            absolute
            for href in parser.links
            if (absolute := urljoin(url, href)).startswith("http")
            and urlparse(absolute).netloc == host
            and absolute.split("#")[0].rstrip("/") != url.rstrip("/")
            and "/wp-admin" not in absolute
            and "wp-login" not in absolute
        )
    )
    text = " ".join(" ".join(parser.text).split())
    return _HttpResult(status, parser.title.strip(), len(text), errors, links, text)


def _check_links(url: str, links: tuple[str, ...], home_text: str = "") -> tuple[LinkCheck, ...]:
    del url
    checks: list[LinkCheck] = []
    for link in links[:MAX_LINKS]:
        status, body = _fetch(link)
        hata = next(iter(page_error_lines(body)), "")
        parser = _PageText()
        with contextlib.suppress(Exception):
            parser.feed(body)
        text = " ".join(" ".join(parser.text).split())
        same = bool(home_text) and len(home_text) >= MIN_VISIBLE_CHARS and text == home_text
        checks.append(LinkCheck(link.split("#")[0], status, hata, same_as_home=same))
    return tuple(checks)


def _fetch(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_S) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, ""
    except (ValueError, http.client.InvalidURL):
        # Ölçüldü (4 Ekim): şablondaki PHP hatası bağlantı adresine karıştı
        # ("/<br /><b>Fatal error…") ve InvalidURL bütün önizleme aracını düşürdü.
        # Bozuk adres açılmayan bağlantı olarak raporlanır; ölçüm sürer.
        return 0, ""


@dataclass(frozen=True, slots=True)
class _BrowserResult:
    screenshot: bytes | None = None
    console: tuple[str, ...] = ()
    measured: dict[str, Any] | None = None
    failed: tuple[str, ...] = ()
    external_hosts: tuple[str, ...] = ()


async def _browser_probe(
    url: str, measure_script: str | None, viewport: tuple[int, int]
) -> _BrowserResult:
    from playwright.async_api import async_playwright

    errors: list[str] = []
    failed: list[str] = []
    host = urlparse(url).netloc
    measured: dict[str, Any] | None = None

    external: list[str] = []

    def _note_response(status: int, target: str) -> None:
        parsed = urlparse(target)
        if parsed.netloc and parsed.netloc != host:
            external.append(parsed.netloc)
            return  # dış servis hatası sitenin sorunu değildir
        if status >= 400 and target.rstrip("/") != url.rstrip("/"):
            failed.append(f"HTTP {status} {parsed.path}")

    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        try:
            page = await browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
            page.on("pageerror", lambda exc: errors.append(str(exc)[:160]))
            page.on(
                "console",
                lambda msg: errors.append(msg.text[:160]) if msg.type == "error" else None,
            )
            page.on("response", lambda response: _note_response(response.status, response.url))
            await page.goto(url, timeout=PROBE_TIMEOUT_S * 1000, wait_until="load")
            shot = await page.screenshot(type="jpeg", quality=70)
            if measure_script is not None:
                with contextlib.suppress(Exception):
                    measured = await page.evaluate(measure_script, {})
        finally:
            await browser.close()
    return _BrowserResult(
        shot,
        tuple(dict.fromkeys(errors)),
        measured,
        tuple(dict.fromkeys(failed)),
        tuple(dict.fromkeys(external)),
    )


class _PageText(HTMLParser):
    """Başlık, görünür metin ve bağlantılar (script/style hariç)."""

    _HIDDEN = frozenset({"script", "style", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.text: list[str] = []
        self.links: list[str] = []
        self._stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack.append(tag)
        if tag == "a":
            href = dict(attrs).get("href")
            if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        if "title" in self._stack:
            self.title += data
        elif not self._HIDDEN.intersection(self._stack):
            self.text.append(data.strip())

"""Üretilen sayfayı gerçekten açıp ÖLÇEN doğrulama kapısı.

Metin desenleriyle yakalanamayan ama nesnel olan hatalar burada bulunur: konsol
hataları, yüklenemeyen kaynaklar ve yatay taşma. Kullanıcı bunları şartnamede açıkça
yasaklamıştı ("yatay taşma veya konsol hatası bulunmasın") ve statik tarama üçünü de
göremiyordu — 24 konsol hatasını ancak sayfayı açan insan fark etti.

Kapsam bilinçli olarak DAR: yalnızca ölçülebilir ve tartışmasız bozuk olan şeyler.
Hizalama, boşluk ritmi, renk uyumu gibi tasarım yargıları buraya GİRMEZ; onlar
mekanik olarak karara bağlanamaz ve kural yazmak çıktıyı tektipleştirir.

Playwright ZORUNLU BAĞIMLILIK DEĞİLDİR (`fusion-cli[web]` ekstrası). Kurulu değilse
ya da tarayıcı ikilisi indirilmemişse kapı sessizce geçer: doğrulama bir iyileştirmedir,
turu düşürmesi kabul edilemez.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ...core.tools import ToolContext
from ...core.verification import VerificationResult

_logger = logging.getLogger(__name__)

#: Yatay taşma sınanacak genişlikler: mobil, tablet, masaüstü.
VIEWPORTS = (375, 768, 1440)
#: Sayfanın yüklenmesi için tanınan süre.
PAGE_TIMEOUT_MS = 15_000
#: Bir sayfa için bildirilecek en fazla farklı kaynak/hata (talimat okunabilir kalsın).
MAX_ITEMS_PER_KIND = 5


@dataclass(frozen=True, slots=True)
class PageObservation:
    """Bir sayfanın açıldığında gözlenen hali. Yorum yok, ölçüm var."""

    name: str
    console_errors: tuple[str, ...] = ()
    failed_requests: tuple[str, ...] = ()
    #: (genişlik, gerçek içerik genişliği) — yalnızca taşma olan genişlikler.
    overflowing: tuple[tuple[int, int], ...] = ()


def page_findings(observations: Sequence[PageObservation]) -> tuple[str, ...]:
    """Gözlemleri modele verilecek somut talimatlara çevir. Saf fonksiyon."""
    bulgular: list[str] = []
    for page in observations:
        bulgular.extend(_console(page))
        bulgular.extend(_requests(page))
        bulgular.extend(_overflow(page))
    return tuple(bulgular)


def _console(page: PageObservation) -> list[str]:
    benzersiz = _tekille(page.console_errors)
    if not benzersiz:
        return []
    # Sayı FARKLI hata sayısıdır: sayfa her genişlik için yeniden yüklendiğinden ham
    # sayım üçe katlanır ve modele şişirilmiş bir tablo sunar.
    return [
        f"{page.name} açıldığında {_farkli_sayi(page.console_errors)} konsol hatası "
        "veriyor: " + "; ".join(benzersiz)
    ]


def _requests(page: PageObservation) -> list[str]:
    benzersiz = _tekille(page.failed_requests)
    if not benzersiz:
        return []
    return [
        f"{page.name} içinde {_farkli_sayi(page.failed_requests)} kaynak yüklenemedi "
        "(sayfa kırık görünür): " + "; ".join(benzersiz)
    ]


def _overflow(page: PageObservation) -> list[str]:
    if not page.overflowing:
        return []
    detay = ", ".join(
        f"{genislik}px ekranda içerik {gercek}px" for genislik, gercek in page.overflowing
    )
    return [
        f"{page.name} yatay taşma yapıyor ({detay}); sayfa yana kayıyor. "
        "Taşan öğeyi bul ve genişliğini sınırla."
    ]


def _farkli_sayi(items: Sequence[str]) -> int:
    """Kaç FARKLI sorun var? Aynı kaynağın üç kez düşmesi üç sorun değildir."""
    return len(set(items))


def _tekille(items: Sequence[str]) -> list[str]:
    """Tekrarları at ve listeyi kısalt: 12 kırık görsel 12 satır bulgu üretmemeli."""
    return list(dict.fromkeys(items))[:MAX_ITEMS_PER_KIND]


def _playwright_available() -> bool:
    """Opsiyonel ekstra kurulu mu? Import maliyeti yalnızca gerektiğinde ödenir."""
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False
    return True


class BrowserVerifier:
    """Agent'ın yazdığı HTML sayfalarını açar ve ölçer."""

    def __init__(self, tool_context: ToolContext) -> None:
        self._context = tool_context

    async def verify(self) -> VerificationResult:
        pages = [
            path
            for path in sorted(self._context.touched)
            if path.suffix.lower() in (".html", ".htm") and path.is_file()
        ]
        # HTML yoksa tarayıcıyı hiç yoklamayız: ölçülecek bir şey yok.
        if not pages:
            return VerificationResult(ok=True)
        if not _playwright_available():
            return VerificationResult(ok=True)

        try:
            observations = await self._observe(pages)
        except Exception as exc:
            # Tarayıcı ikilisi indirilmemiş, sandbox izin vermemiş, uç çökmüş olabilir.
            # Doğrulama bir iyileştirmedir; turu düşürmesi kabul edilemez.
            _logger.debug("tarayıcı doğrulaması atlandı: %s", exc)
            return VerificationResult(ok=True)

        findings = page_findings(observations)
        if not findings:
            return VerificationResult(ok=True)
        return VerificationResult(
            ok=False, summary=f"tarayıcıda {len(findings)} sorun", findings=findings
        )

    async def _observe(self, pages: list[Path]) -> list[PageObservation]:
        from playwright.async_api import async_playwright

        observations: list[PageObservation] = []
        async with async_playwright() as driver:
            browser = await driver.chromium.launch()
            try:
                for path in pages:
                    observations.append(await self._observe_page(browser, path))
            finally:
                await browser.close()
        return observations

    async def _observe_page(self, browser: object, path: Path) -> PageObservation:
        console_errors: list[str] = []
        failed: list[str] = []
        overflowing: list[tuple[int, int]] = []

        page = await browser.new_page()  # type: ignore[attr-defined]
        page.on("pageerror", lambda exc: console_errors.append(str(exc)[:120]))
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text[:120]) if msg.type == "error" else None,
        )
        page.on("requestfailed", lambda req: failed.append(req.url[:120]))

        try:
            for width in VIEWPORTS:
                await page.set_viewport_size({"width": width, "height": 900})
                await page.goto(path.as_uri(), timeout=PAGE_TIMEOUT_MS, wait_until="load")
                actual = await page.evaluate("document.documentElement.scrollWidth")
                # 1px tolerans: yuvarlama farkı taşma sayılmamalı.
                if isinstance(actual, int | float) and actual > width + 1:
                    overflowing.append((width, int(actual)))
        finally:
            await page.close()

        return PageObservation(
            name=path.name,
            console_errors=tuple(console_errors),
            failed_requests=tuple(failed),
            overflowing=tuple(overflowing),
        )

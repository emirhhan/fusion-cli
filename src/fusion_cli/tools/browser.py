"""Etkileşimli tarayıcı araçları — agent'ın gözü ve eli.

`web_fetch` bir sayfanın HTML'ini çeker ve orada durur: form dolduramaz, düğmeye
basamaz, oturum açamaz. Ölçülen gerçek zarar buydu — şifre korumalı bir mağazanın
adresi 200 döndü, gelen metin kapının kendisiydi ve agent istenen siteyi hiç göremedi.

Buradaki araçlar tek bir sayfayı tur boyunca AÇIK tutar; "alana yaz → gönder →
açılan sayfayı oku" zinciri üç ayrı çağrıyla yürür. Oturum `ToolContext.browser`
taşıyıcısında durur, modül-global değildir.

Playwright ZORUNLU BAĞIMLILIK DEĞİLDİR (`fusion-cli[web]`). Kurulu değilse araçlar
çalışmaz ama anlaşılır bir kurulum talimatı döner; uygulama açılmaya devam eder.
"""

from __future__ import annotations

from typing import Any

from ..core.constants import MAX_OUTPUT_CHARS, truncate_notice
from ..core.tools import ToolArgs, ToolContext, ToolResult
from .args import optional_str, require_str
from .files import resolve_path
from .web import access_wall_notice, url_block_reason

#: Sayfa yüklenmesi ve öğe bekleme için üst sınır (ms). Tarayıcı etkileşimi ağdan
#: yavaştır; `WEB_TIMEOUT_S` bir HTTP isteği bütçesidir ve buraya uymaz.
PAGE_TIMEOUT_MS = 30_000
#: Bir öğenin görünür olmasını bekleme sınırı (ms). Sayfa yüklüyse öğe hızlı gelir;
#: gelmiyorsa seçici yanlıştır ve modeli uzun süre bekletmenin faydası yoktur.
SELECTOR_TIMEOUT_MS = 10_000

_KURULUM_TALIMATI = (
    "Tarayıcı aracı kullanılamıyor: playwright kurulu değil. Kurulum:\n"
    "  pip install 'fusion-cli[web]'\n"
    "  playwright install chromium\n"
    "Kurulamıyorsa bu işi tarayıcı olmadan yapamazsın — kullanıcıya söyle."
)


async def browser_open(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bir adresi aç (oturum yoksa başlat) ve sayfanın görünür metnini döndür."""
    url = require_str(args, "url")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    # SSRF doğrulaması `web_fetch` ile AYNI kapıdan geçer: tarayıcı olması adresi
    # güvenli yapmaz, tersine yerel ağa erişim için daha güçlü bir araçtır.
    reason = url_block_reason(url)
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")

    page, hata = await _sayfa(context)
    if page is None:
        return ToolResult.failure(hata)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except Exception as exc:
        return ToolResult.failure(f"Sayfa açılamadı: {url} ({type(exc).__name__}: {exc})")
    return await _sayfa_ozeti(page, "açıldı")


async def browser_type(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bir alana metin yaz; `submit` verilirse ardından Enter'a bas."""
    selector = require_str(args, "selector")
    text = require_str(args, "text")
    submit = bool(args.get("submit"))

    page, hata = await _sayfa(context)
    if page is None:
        return ToolResult.failure(hata)
    if not page.url or page.url == "about:blank":
        return ToolResult.failure("Önce browser_open ile bir sayfa aç.")
    try:
        alan = page.locator(selector).first
        await alan.wait_for(state="visible", timeout=SELECTOR_TIMEOUT_MS)
        await alan.fill(text)
        if submit:
            await alan.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except Exception as exc:
        return ToolResult.failure(_secici_hatasi(selector, exc))
    return await _sayfa_ozeti(page, "yazıldı ve gönderildi" if submit else "yazıldı")


async def browser_click(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bir öğeye tıkla ve sayfanın yeni halini döndür."""
    selector = require_str(args, "selector")

    page, hata = await _sayfa(context)
    if page is None:
        return ToolResult.failure(hata)
    if not page.url or page.url == "about:blank":
        return ToolResult.failure("Önce browser_open ile bir sayfa aç.")
    try:
        hedef = page.locator(selector).first
        await hedef.wait_for(state="visible", timeout=SELECTOR_TIMEOUT_MS)
        await hedef.click(timeout=SELECTOR_TIMEOUT_MS)
        await page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except Exception as exc:
        return ToolResult.failure(_secici_hatasi(selector, exc))
    return await _sayfa_ozeti(page, "tıklandı")


async def browser_read(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Açık sayfanın güncel adresini, başlığını ve görünür metnini oku."""
    del args
    page, hata = await _sayfa(context, baslatma=False)
    if page is None:
        return ToolResult.failure(hata)
    return await _sayfa_ozeti(page, "okundu")


async def browser_screenshot(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Açık sayfanın ekran görüntüsünü diske yaz.

    Görsel, metin çıkarımının kaçırdığı düzeni taşır: bir siteyi taklit ederken
    yerleşimi ancak görüntüden anlarsın.
    """
    page, hata = await _sayfa(context, baslatma=False)
    if page is None:
        return ToolResult.failure(hata)

    hedef = resolve_path(context, optional_str(args, "path", "ekran-goruntusu.png"))
    hedef.parent.mkdir(parents=True, exist_ok=True)
    tam_sayfa = args.get("full_page", True)
    try:
        context.changes.record(hedef)
        await page.screenshot(path=str(hedef), full_page=bool(tam_sayfa))
    except Exception as exc:
        return ToolResult.failure(f"Ekran görüntüsü alınamadı ({type(exc).__name__}: {exc})")
    context.touched.add(hedef)
    return ToolResult(f"ekran görüntüsü yazıldı: {hedef}")


async def browser_close(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Tarayıcıyı kapat. Tur sonunda motor da kapatır; bu erken bırakma içindir."""
    del args
    if not context.browser.is_open:
        return ToolResult("tarayıcı zaten kapalı")
    await context.browser.close()
    return ToolResult("tarayıcı kapatıldı")


# --------------------------------------------------------------------------- #
# İç yardımcılar
# --------------------------------------------------------------------------- #


async def _sayfa(context: ToolContext, *, baslatma: bool = True) -> tuple[Any, str]:
    """Etkin sayfayı getir; yoksa (ve izin varsa) oturumu başlat.

    Dönüş: (sayfa, hata). Sayfa `None` ise hata doludur.
    """
    oturum = context.browser
    if oturum.is_open:
        return oturum.page, ""
    if not baslatma:
        return None, "Açık bir sayfa yok — önce browser_open ile bir adres aç."

    try:
        # Ağır ve OPSİYONEL bağımlılık: yalnızca araç gerçekten çağrıldığında yüklenir.
        from playwright.async_api import async_playwright
    except ImportError:
        return None, _KURULUM_TALIMATI

    try:
        oturum.playwright = await async_playwright().start()
        oturum.browser = await oturum.playwright.chromium.launch(headless=True)
        oturum.page = await oturum.browser.new_page()
    except Exception as exc:
        await oturum.close()
        return None, (
            f"Tarayıcı başlatılamadı ({type(exc).__name__}: {exc}). "
            "Tarayıcı ikilisi eksikse: playwright install chromium"
        )
    return oturum.page, ""


async def _sayfa_ozeti(page: Any, eylem: str) -> ToolResult:
    """Sayfanın adresini, başlığını ve görünür metnini tek bir sonuca topla."""
    try:
        url = page.url
        baslik = await page.title()
        govde = str(await page.locator("body").inner_text(timeout=SELECTOR_TIMEOUT_MS))
    except Exception as exc:
        return ToolResult.failure(f"Sayfa okunamadı ({type(exc).__name__}: {exc})")

    metin = truncate_notice(govde.strip(), MAX_OUTPUT_CHARS, ne="sayfa metni") or "(boş sayfa)"
    satirlar = [f"{eylem}: {url}", f"başlık: {baslik}"]
    # Duvar tespiti `web_fetch` ile AYNI fonksiyondan geçer. Tarayıcıda duvar
    # AŞILABİLİR (şifre yazılır, giriş yapılır) — bu yüzden uyarı burada da
    # gösterilir ama anlamı farklıdır: "içerik bu değil, kapıyı geç".
    duvar = access_wall_notice(govde)
    if duvar:
        satirlar.append(duvar)
    satirlar.append(metin)
    return ToolResult("\n".join(satirlar))


def _secici_hatasi(selector: str, exc: Exception) -> str:
    return (
        f"Öğe bulunamadı ya da etkileşilemedi: {selector} "
        f"({type(exc).__name__}). browser_read ile sayfanın güncel halini oku ve "
        "seçiciyi ORADAN doğrula; seçici uydurma."
    )

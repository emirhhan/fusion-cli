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

import asyncio
import contextlib
import weakref
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..config.browser_profiles import BrowserProfileStore, default_browser_profile_store
from ..core.browser_session import BrowserSession
from ..core.constants import MAX_OUTPUT_CHARS, truncate_notice
from ..core.cookie_files import cookies_from_storage_state, origins_from_storage_state
from ..core.errors import BrowserProfileError
from ..core.tools import ToolArgs, ToolContext, ToolEffect, ToolResult
from .args import is_truthy, optional_str, require_str
from .browser_guard import blocked_hint, install_request_guard
from .browser_shared import control_gate
from .browser_target import TargetError, fill_or_select, resolve
from .files import writable_path
from .mirror import (
    MAX_ASSET_BYTES,
    MAX_ASSETS,
    MirroredAsset,
    asset_local_path,
    is_mirrorable,
    mirror_summary,
    rewrite_links,
)
from .web import access_wall_notice, browser_block_reason

#: Sayfa yüklenmesi ve öğe bekleme için üst sınır (ms). Tarayıcı etkileşimi ağdan
#: yavaştır; `WEB_TIMEOUT_S` bir HTTP isteği bütçesidir ve buraya uymaz.
PAGE_TIMEOUT_MS = 30_000
#: Bir öğenin görünür olmasını bekleme sınırı (ms). Sayfa yüklüyse öğe hızlı gelir;
#: gelmiyorsa seçici yanlıştır ve modeli uzun süre bekletmenin faydası yoktur.
SELECTOR_TIMEOUT_MS = 10_000
#: Aynalamada ağın sakinleşmesi için beklenen süre (ms). Tembel yüklenen görseller
#: ancak burada gelir; sakinleşmeyen siteler (canlı bağlantı tutanlar) bu süre
#: sonunda elde olanla devam eder.
NETWORK_IDLE_MS = 15_000

_KURULUM_TALIMATI = (
    "Tarayıcı aracı kullanılamıyor: playwright kurulu değil. Kurulum:\n"
    "  pip install 'fusion-cli[web]'\n"
    "  playwright install chromium\n"
    "Kurulamıyorsa bu işi tarayıcı olmadan yapamazsın — kullanıcıya söyle."
)


_LOCAL_PREFIXES = ("localhost", "127.0.0.1", "[::1]")
SHARED_HEADED_NOTE = (
    "not: headed yok sayıldı; tarayıcı kullanıcıyla paylaşılıyor ve Tarayıcı panelinde görünür."
)


def normalize_url(raw: str) -> str:
    """Şemasız adrese şema ekle: yerel sunucu `http://` (TLS yok), diğerleri `https://`.

    Ölçüldü (30 Ekim): `localhost:3000` otomatik `https://` alıp TLS hatası veriyordu.
    """
    if raw.startswith(("http://", "https://")):
        return raw
    return f"http://{raw}" if raw.lower().startswith(_LOCAL_PREFIXES) else f"https://{raw}"


def _full_page(args: ToolArgs) -> bool:
    """`full_page` varsayılan açık; `"false"` metni de kapatır (eskiden truthy sayılıyordu)."""
    raw = args.get("full_page")
    return True if raw is None else is_truthy(raw)


async def browser_open(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bir adresi aç (oturum yoksa başlat) ve sayfanın görünür metnini döndür.

    `profile` (P-023): `fusion browser` ile kurulan kullanıcı oturumu profili; çerezleri
    yalnız onaylı alan adlarında yüklenir. `headed`: pencere görünür açılır.
    """
    url = normalize_url(require_str(args, "url"))
    # SSRF doğrulaması `web_fetch` ile AYNI kapıdan geçer: tarayıcı olması adresi
    # güvenli yapmaz, tersine yerel ağa erişim için daha güçlü bir araçtır.
    reason = browser_block_reason(url, context.local_origins)
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")

    profile = optional_str(args, "profile", "").strip()
    headed = is_truthy(args.get("headed"))
    shared_note = ""
    if headed and context.browser.persistent:
        # Paylaşılan tarayıcı (P-045) panelde ya da kullanıcının penceresinde zaten görünür;
        # `headed` ikinci bir yerel pencere açardı (ölçüldü 31 Ekim, inceleme).
        headed = False
        shared_note = SHARED_HEADED_NOTE
    page, hata = await _sayfa(context, profile=profile, headed=headed)
    if page is None:
        return ToolResult.failure(hata)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except Exception as exc:
        return ToolResult.failure(
            f"Sayfa açılamadı: {url} ({type(exc).__name__}: {exc}){blocked_hint(exc)}"
        )
    result = _with_profile_note(await _sayfa_ozeti(page, "açıldı"), context.browser)
    if shared_note and result.ok:
        result = replace(result, output=f"{shared_note}\n{result.output}")
    return result


async def browser_open_effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect:
    """Çerezsiz açılış yalnız okur; profil YÜKLENECEKSE kullanıcının oturumu ajana açılır.

    Ölçüldü (31 Ekim): `browser_open` değiştirici sayılmadığı için `default_profile`
    ya da modelin bildiği bir profil adı hiç sorulmadan yükleniyordu; sayfadaki enjekte
    talimat ajanı girişli siteye götürebilirdi. Açık oturumda yeni yükleme olmaz: aynı
    profil zaten onaylanmıştır, farklı profil isteğini araç kendisi reddeder.
    """
    if context is None:
        return ToolEffect.REMOTE_READ
    oturum = context.browser
    profile = optional_str(args, "profile", "").strip()
    if _will_load_profile(oturum, profile):
        return ToolEffect.REMOTE_SESSION
    return ToolEffect.REMOTE_READ


def _will_load_profile(oturum: BrowserSession, profile: str) -> bool:
    return not _is_open(oturum) and oturum.profiles_enabled and bool(profile or oturum.profile_name)


async def browser_type_effect(args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
    """Girişli profil etkinken yazma sayfayla etkileşimdir, `submit` uzak yazmadır.

    Profilsiz tarayıcıda eski sınıflandırma (yerel) korunur: oturum taşımayan sayfada
    form göndermenin kullanıcı hesabına etkisi yoktur.
    """
    if context is None or not context.browser.active_profile:
        return None
    return ToolEffect.REMOTE_WRITE if is_truthy(args.get("submit")) else ToolEffect.REMOTE_INTERACT


async def browser_click_effect(_args: ToolArgs, context: ToolContext | None) -> ToolEffect | None:
    """Girişli profil etkinken tıklama kullanıcının hesabıyla iş yapabilir: sorulur."""
    if context is None or not context.browser.active_profile:
        return None
    return ToolEffect.REMOTE_WRITE


async def browser_type(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bir alana metin yaz; `submit` verilirse ardından Enter'a bas."""
    selector = require_str(args, "selector")
    text = require_str(args, "text")
    submit = is_truthy(args.get("submit"))

    page, hata = await _sayfa(context)
    if page is None:
        return ToolResult.failure(hata)
    if not page.url or page.url == "about:blank":
        return ToolResult.failure("Önce browser_open ile bir sayfa aç.")
    try:
        hedef = await resolve(page, selector, SELECTOR_TIMEOUT_MS)
        ne_oldu = await fill_or_select(hedef, text)
        if submit:
            await hedef.locator.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except TargetError as exc:
        return ToolResult.failure(str(exc))
    except Exception as exc:
        return ToolResult.failure(_secici_hatasi(selector, exc))
    return await _sayfa_ozeti(page, f"{ne_oldu}{' ve gönderildi' if submit else ''}")


async def browser_click(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bir öğeye tıkla ve sayfanın yeni halini döndür."""
    selector = require_str(args, "selector")

    page, hata = await _sayfa(context)
    if page is None:
        return ToolResult.failure(hata)
    if not page.url or page.url == "about:blank":
        return ToolResult.failure("Önce browser_open ile bir sayfa aç.")
    try:
        hedef = await resolve(page, selector, SELECTOR_TIMEOUT_MS)
        await hedef.locator.click(timeout=SELECTOR_TIMEOUT_MS)
        await page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except TargetError as exc:
        return ToolResult.failure(str(exc))
    except Exception as exc:
        return ToolResult.failure(_secici_hatasi(selector, exc))
    return await _sayfa_ozeti(page, f"tıklandı ({hedef.description})")


async def browser_read(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Açık sayfanın güncel adresini, başlığını ve görünür metnini oku."""
    del args
    page, hata = await _sayfa(context, baslatma=False)
    if page is None:
        return ToolResult.failure(hata)
    return await _sayfa_ozeti(page, "okundu")


async def browser_tabs_list(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Turun tarayıcısındaki sekmeleri ve etkin sekmeyi listele."""
    del args
    if not context.browser.is_open:
        return ToolResult.failure("Açık bir tarayıcı yok — önce browser_open kullan.")
    if engel := await control_gate(context.browser):
        return ToolResult.failure(engel)
    pages = await context.browser.pages()
    rows: list[str] = []
    for index, page in enumerate(pages, start=1):
        title = await page.title()
        marker = "*" if page is context.browser.page else " "
        rows.append(f"{marker} {index}. {title} — {page.url}")
    return ToolResult("\n".join(rows) if rows else "Açık sekme yok.")


async def browser_tab_select(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Listelenen sekmeye geç ve güncel sayfayı oku."""
    raw_index = args.get("index")
    if not isinstance(raw_index, int) or isinstance(raw_index, bool) or raw_index < 1:
        return ToolResult.failure("'index' 1'den başlayan bir tam sayı olmalı.")
    if not context.browser.is_open:
        return ToolResult.failure("Açık bir tarayıcı yok — önce browser_open kullan.")
    if engel := await control_gate(context.browser):
        return ToolResult.failure(engel)
    pages = await context.browser.pages()
    if raw_index > len(pages):
        return ToolResult.failure(f"{raw_index} numaralı sekme yok; browser_tabs_list kullan.")
    context.browser.page = pages[raw_index - 1]
    return await _sayfa_ozeti(context.browser.page, "sekme seçildi")


async def browser_tab_open(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Aynı oturumda yeni sekme aç ve izin verilen adrese git."""
    url = normalize_url(require_str(args, "url"))
    reason = browser_block_reason(url, context.local_origins)
    if reason is not None:
        return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
    page, error = await _sayfa(context)
    if page is None:
        return ToolResult.failure(error)
    new_page = None
    try:
        new_page = await context.browser.context.new_page()
        await new_page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except Exception as exc:
        if new_page is not None:
            await new_page.close()
        return ToolResult.failure(
            f"Sekme açılamadı ({type(exc).__name__}: {exc}){blocked_hint(exc)}"
        )
    context.browser.page = new_page
    return await _sayfa_ozeti(new_page, "sekme açıldı")


async def browser_screenshot(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Açık sayfanın ekran görüntüsünü diske yaz.

    Görsel, metin çıkarımının kaçırdığı düzeni taşır: bir siteyi taklit ederken
    yerleşimi ancak görüntüden anlarsın.
    """
    page, hata = await _sayfa(context, baslatma=False)
    if page is None:
        return ToolResult.failure(hata)

    hedef = writable_path(context, optional_str(args, "path", "ekran-goruntusu.png"))
    hedef.parent.mkdir(parents=True, exist_ok=True)
    try:
        context.changes.record(hedef)
        await page.screenshot(path=str(hedef), full_page=_full_page(args))
        context.changes.record_applied(hedef)
    except Exception as exc:
        return ToolResult.failure(f"Ekran görüntüsü alınamadı ({type(exc).__name__}: {exc})")
    context.touched.add(hedef)
    return ToolResult(f"ekran görüntüsü yazıldı: {hedef}")


async def browser_mirror(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Bir sayfayı yüklediği kaynaklarla birlikte diske aynala.

    Açık oturumu kullanır: şifre kapısı `browser_type` ile geçildiyse ayna da o
    oturumu görür. `url` verilmezse ETKİN sayfa aynalanır — kapıyı geçtikten sonra
    "burayı indir" demenin doğal yolu budur.
    """
    hedef = writable_path(context, optional_str(args, "path", "ayna"))
    page, hata = await _sayfa(context)
    if page is None:
        return ToolResult.failure(hata)

    url = optional_str(args, "url", "")
    yakalanan: dict[str, bytes] = {}
    kesildi = False

    async def _yanit(response: Any) -> None:
        nonlocal kesildi
        adres = response.url
        if adres in yakalanan or not response.ok:
            return
        if not is_mirrorable(adres, response.headers.get("content-type", "")):
            return
        if len(yakalanan) >= MAX_ASSETS:
            kesildi = True
            return
        try:
            govde = await response.body()
        except Exception:
            return
        if len(govde) <= MAX_ASSET_BYTES:
            yakalanan[adres] = govde

    page.on("response", _yanit)
    try:
        if url:
            url = normalize_url(url)
            reason = browser_block_reason(url, context.local_origins)
            if reason is not None:
                return ToolResult.failure(f"Bu adrese erişilemez: {reason}")
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        else:
            # Etkin sayfa zaten açık; kaynakları dinleyebilmek için yeniden yükle.
            await page.reload(wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        # Tembel yüklenen görseller ancak ağ sakinleşince gelir. Sakinleşmezse
        # (canlı bağlantı tutan siteler) elde olanla devam edilir.
        with contextlib.suppress(Exception):
            await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_MS)
        html = await page.content()
    except Exception as exc:
        return ToolResult.failure(f"Ayna alınamadı ({type(exc).__name__}: {exc})")
    finally:
        page.remove_listener("response", _yanit)

    return _aynayi_yaz(context, hedef, html, yakalanan, kesildi)


def _aynayi_yaz(
    context: ToolContext,
    hedef: Path,
    html: str,
    yakalanan: dict[str, bytes],
    kesildi: bool,
) -> ToolResult:
    """Yakalanan kaynakları ve yeniden yazılmış HTML'i diske indir."""
    (hedef / "assets").mkdir(parents=True, exist_ok=True)

    yazilan: list[MirroredAsset] = []
    atlanan = 0
    for adres, govde in yakalanan.items():
        yerel = asset_local_path(adres)
        dosya = hedef / yerel
        try:
            dosya.parent.mkdir(parents=True, exist_ok=True)
            context.changes.record(dosya)
            dosya.write_bytes(govde)
            context.changes.record_applied(dosya)
        except OSError:
            atlanan += 1
            continue
        context.touched.add(dosya)
        yazilan.append(MirroredAsset(url=adres, local=yerel))

    sayfa = hedef / "index.html"
    context.changes.record(sayfa)
    sayfa.write_text(rewrite_links(html, tuple(yazilan)), encoding="utf-8")
    context.changes.record_applied(sayfa)
    context.touched.add(sayfa)
    return ToolResult(mirror_summary(hedef, tuple(yazilan), atlanan, kesildi))


async def browser_close(args: ToolArgs, context: ToolContext) -> ToolResult:
    """Tarayıcıyı kapat. Tur sonunda motor da kapatır; bu erken bırakma içindir."""
    del args
    if not context.browser.is_open:
        return ToolResult("tarayıcı zaten kapalı")
    if context.browser.persistent:
        # Paylaşılan tarayıcı (panel / `/tarayici`) kullanıcınındır; ajan onu kapatamaz.
        return ToolResult("tarayıcı kullanıcıyla paylaşılıyor; açık bırakıldı (panelden kapanır)")
    await context.browser.close()
    return ToolResult("tarayıcı kapatıldı")


# --------------------------------------------------------------------------- #
# İç yardımcılar
# --------------------------------------------------------------------------- #


#: Oturum başına başlatma kilidi: iki eşzamanlı ilk çağrı iki Chromium başlatıp birini
#: sızdırıyordu (ölçüldü, 30 Ekim).
_START_LOCKS: weakref.WeakKeyDictionary[BrowserSession, asyncio.Lock] = weakref.WeakKeyDictionary()


def start_lock(oturum: BrowserSession) -> asyncio.Lock:
    """Oturumun başlatma kilidi; ajan aracı ve Tarayıcı paneli (P-045) AYNI kilidi kullanır.

    Ölçüldü (31 Ekim, inceleme): panelin ayrı kilidi vardı; panel ve ajan aynı paylaşılan
    oturumu eşzamanlı açınca ikinci Chromium birincinin üstüne yazılıp sızıyordu.
    """
    return _START_LOCKS.setdefault(oturum, asyncio.Lock())


async def _sayfa(
    context: ToolContext, *, baslatma: bool = True, profile: str = "", headed: bool = False
) -> tuple[Any, str]:
    """Etkin sayfayı getir; yoksa (ve izin varsa) oturumu başlat.

    Dönüş: (sayfa, hata). Sayfa `None` ise hata doludur. Açık oturum başka profille
    sürüyorsa yeniden başlatılmaz: iki profilin çerezleri aynı bağlamda karışmasın.
    """
    oturum = context.browser
    # Kullanıcı devraldıysa (P-045) bırakana kadar beklenir; ajan onunla yarışmaz.
    if engel := await control_gate(oturum):
        return None, engel
    if _is_open(oturum):
        if profile and profile != oturum.active_profile:
            cozum = (
                "profili Tarayıcı panelinden değiştirmesini kullanıcıdan iste"
                if oturum.persistent
                else "önce browser_close çağır"
            )
            return None, (
                f"Tarayıcı zaten '{oturum.active_profile or 'profilsiz'}' oturumuyla açık; "
                f"'{profile}' profili için {cozum}."
            )
        return oturum.page, ""
    if not baslatma:
        return None, "Açık bir sayfa yok — önce browser_open ile bir adres aç."
    async with start_lock(oturum):
        if _is_open(oturum):  # kilidi beklerken başka çağrı başlatmış olabilir
            return oturum.page, ""
        return await start_session(oturum, context.local_origins, profile=profile, headed=headed)


def _is_open(oturum: BrowserSession) -> bool:
    return bool(oturum.is_open)


def _profile_state(
    oturum: BrowserSession, profile: str, store: BrowserProfileStore
) -> tuple[dict[str, object] | None, str]:
    """Yüklenecek profilin `storage_state`'ini getir; (durum, hata) döndür.

    Araç argümanı yapılandırmadaki varsayılanı ezer. Profiller kapalıysa (`browser.
    profiles_enabled: false`) açık istek bile reddedilir — ayar, ajanın kullanıcı
    oturumuna hiç dokunamayacağının güvencesidir.
    """
    name = profile or oturum.profile_name
    if not name:
        return None, ""
    if not oturum.profiles_enabled:
        return None, (
            "Tarayıcı profilleri kapalı (browser.profiles_enabled: false); "
            "çerezsiz devam etmek için profile argümanını kaldır."
        )
    try:
        state = store.storage_state(name)
    except BrowserProfileError as error:
        return None, f"Tarayıcı profili yüklenemedi: {error}"
    oturum.active_profile = name
    return state, ""


async def start_session(
    oturum: BrowserSession,
    local_origins: set[str],
    *,
    profile: str = "",
    headed: bool = False,
    store: BrowserProfileStore | None = None,
) -> tuple[Any, str]:
    """Oturumu başlat: Chromium + (varsa) profil çerezleri + istek kapısı; (sayfa, hata).

    Tarayıcı paneli (P-045) de bu yoldan açar: güvenlik kapısı ve profil kuralları ajanla
    AYNIDIR. `local_origins` canlı kümedir (izin verilen yerel adresler).
    """
    try:
        # Ağır ve OPSİYONEL bağımlılık: yalnızca araç gerçekten çağrıldığında yüklenir.
        from playwright.async_api import async_playwright
    except ImportError:
        return None, _KURULUM_TALIMATI

    store = store or default_browser_profile_store()
    state, hata = _profile_state(oturum, profile, store)
    if hata:
        return None, hata
    headless = oturum.headless and not headed
    try:
        oturum.playwright = await async_playwright().start()
        oturum.browser = await oturum.playwright.chromium.launch(headless=headless)
        oturum.context = (
            await oturum.browser.new_context(storage_state=state)
            if state is not None
            else await oturum.browser.new_context()
        )
        # Yönlendirme, alt kaynak ve yeni sekme istekleri de `browser_block_reason`
        # kapısından geçer; yalnız ilk adresi denetlemek yetmezdi (T1-07).
        await install_request_guard(oturum.context, local_origins)
        oturum.page = await oturum.context.new_page()
    except Exception as exc:
        await oturum.close()
        return None, (
            f"Tarayıcı başlatılamadı ({type(exc).__name__}: {exc}). "
            "Tarayıcı ikilisi eksikse: playwright install chromium"
        )
    # Kapanışta tazelenen oturum geri yazılır; hata core'da loglanır, kapanışı kesmez.
    # Her başlatmada YENİDEN belirlenir: profilsiz açılış eski yazıcıyı devralmaz.
    oturum.state_saver = _state_saver(store, oturum.active_profile) if state is not None else None
    return oturum.page, ""


def _state_saver(store: BrowserProfileStore, name: str) -> Callable[[dict[str, Any]], None]:
    def _save(state: dict[str, Any]) -> None:
        store.update_cookies(
            name, cookies_from_storage_state(state), origins_from_storage_state(state)
        )

    return _save


def _with_profile_note(result: ToolResult, oturum: BrowserSession) -> ToolResult:
    """Hangi profille açıldığı sonucun ilk satırında yazsın; çerez değeri asla yazılmaz."""
    if not result.ok or not oturum.active_profile:
        return result
    return replace(result, output=f"profil: {oturum.active_profile}\n{result.output}")


async def _sayfa_ozeti(page: Any, eylem: str) -> ToolResult:
    """Sayfanın adresini, başlığını ve görünür metnini tek bir sonuca topla.

    Tıklama navigasyon başlattıysa okuma sırasında "Execution context was destroyed"
    oluşabilir: yükleme beklenip BİR KEZ yeniden denenir. Yine okunamazsa eylemin
    YAPILDIĞI söylenir; yoksa model "olmadı" sanıp tekrar tıklar (çift gönderim).
    """
    for deneme in range(2):
        try:
            url = page.url
            baslik = await page.title()
            govde = str(await page.locator("body").inner_text(timeout=SELECTOR_TIMEOUT_MS))
            break
        except Exception as exc:
            gecici = "context was destroyed" in str(exc) or "navigation" in str(exc).lower()
            if deneme == 0 and gecici:
                with contextlib.suppress(Exception):
                    await page.wait_for_load_state("domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                continue
            ek = (
                f" Eylem ({eylem}) YAPILDI ama sonuç okunamadı; AYNI eylemi tekrar etme, "
                "önce browser_read ile sayfayı oku."
                if eylem != "okundu"
                else ""
            )
            return ToolResult.failure(f"Sayfa okunamadı ({type(exc).__name__}: {exc}).{ek}")

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

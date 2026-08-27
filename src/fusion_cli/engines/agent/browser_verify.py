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

import asyncio
import contextlib
import json
import logging
import socket
import time
import urllib.error
import urllib.request
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

#: Sayfanın DÜZENİNİ değiştirebilen dosya uzantıları.
#
# Ölçüldü: model `app/globals.css` değiştirip "lütfen sen kontrol et" diyerek turu
# kapattı ve kapı hiç konuşmadı, çünkü ortada açılacak `.html` dosyası yoktu.
# Next.js/Vite gibi projelerde sayfa çalışma anında üretilir; kapının kör kaldığı
# yer tam da en çok düzen hatası üreten proje türüydü.
LAYOUT_SUFFIXES = frozenset({".css", ".scss", ".sass", ".less", ".tsx", ".jsx", ".vue", ".svelte"})

#: Dev sunucusunun ayağa kalkması için tanınan süre.
#
# Ölçüldü: bu projede `next dev` soğuk başlangıçta ~2 saniyede hazır oluyor, ilk
# derleme birkaç saniye daha alıyor. Sınır cömert tutulur ama sonsuz değildir:
# kapı turu bekletmemelidir.
DEV_SERVER_READY_S = 45.0

#: Dev sunucusu için denenecek port aralığının başı. Kullanıcının kendi sunucusuyla
#: çakışmamak için yaygın portlardan (3000, 5173, 8080) uzak seçilir.
DEV_SERVER_PORT_BASE = 47_300


def touches_layout(paths: Sequence[Path]) -> bool:
    """Değişen dosyalar sayfanın düzenini etkileyebilir mi?

    Dev sunucusu başlatmak pahalıdır (saniyeler); yalnızca düzen değiştiyse yapılır.
    """
    return any(path.suffix.lower() in LAYOUT_SUFFIXES for path in paths)


def dev_server_command(package_json: object) -> list[str] | None:
    """`package.json` içeriğinden dev sunucusu komutunu çıkar; yoksa None.

    Komut UYDURULMAZ: projede kanıtı (tanımlı `dev` betiği) yoksa kapı hiç kurulmaz.
    Bu, `discover_auto_commands` ile aynı disiplin.
    """
    if not isinstance(package_json, dict):
        return None
    scripts = package_json.get("scripts")
    if not isinstance(scripts, dict):
        return None
    if not isinstance(scripts.get("dev"), str):
        return None
    return ["npm", "run", "dev"]


def _free_port() -> int:
    """Boş bir port bul. Sabit port kullanıcının kendi sunucusuyla çakışırdı."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _wait_until_serving(adres: str) -> bool:
    """Sunucu cevap verene kadar bekle; süre dolarsa False.

    Sağlık ölçütü HTTP cevabının GELMESİDİR, durum kodu değil: dev sunucuları
    derleme hatasında da sayfa döndürür ve o sayfayı ölçmek anlamlıdır — ölçtüğümüz
    şey zaten "kullanıcı bunu açtığında ne görüyor".
    """
    bitis = time.monotonic() + DEV_SERVER_READY_S
    while time.monotonic() < bitis:
        try:
            await asyncio.to_thread(urllib.request.urlopen, adres, None, 3)
            return True
        except urllib.error.HTTPError:
            return True
        except (OSError, ValueError):
            await asyncio.sleep(0.5)
    return False


@dataclass(frozen=True, slots=True)
class PageObservation:
    """Bir sayfanın açıldığında gözlenen hali. Yorum yok, ölçüm var."""

    name: str
    console_errors: tuple[str, ...] = ()
    failed_requests: tuple[str, ...] = ()
    #: (genişlik, gerçek içerik genişliği) — yalnızca taşma olan genişlikler.
    overflowing: tuple[tuple[int, int], ...] = ()
    #: (seçici, ikon yüksekliği, kapsayıcı yüksekliği) — orantısız büyük ikonlar.
    oversized_icons: tuple[tuple[str, int, int], ...] = ()
    #: (seçici, kapsayıcı sağ kenarı, öğe sağ kenarı) — kırpılmış, erişilemez içerik.
    clipped: tuple[tuple[str, int, int], ...] = ()
    #: (seçici, genişlik, yükseklik) — dokunma için çok küçük tıklanabilir öğeler.
    small_targets: tuple[tuple[str, int, int], ...] = ()
    #: Başlığı olan ama içi boş bölümlerin seçicileri.
    empty_sections: tuple[str, ...] = ()
    #: (seçici, yükseklik, ekran yüksekliği) — ekranı aşan yardımcı bloklar.
    oversized_blocks: tuple[tuple[str, int, int], ...] = ()


def page_findings_by_severity(
    observations: Sequence[PageObservation],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Tarayıcı ölçümlerini blocking / warning / advisory olarak ayır."""
    blocking: list[str] = []
    warnings: list[str] = []

    for page in observations:
        blocking.extend(_console(page))
        blocking.extend(_requests(page))
        blocking.extend(_overflow(page))
        blocking.extend(_icons(page))
        blocking.extend(_clipped(page))
        blocking.extend(_empty(page))
        blocking.extend(_oversized(page))

        # WCAG ölçümü nesnel ve değerlidir; fakat küçük bir touch target bütün
        # uygulamayı "kırık" sayıp correction turu açtırmamalıdır.
        warnings.extend(_targets(page))

    return tuple(blocking), tuple(warnings), ()


def page_findings(observations: Sequence[PageObservation]) -> tuple[str, ...]:
    """Geriye uyumlu flat bulgu listesi."""
    blocking, warnings, advisories = page_findings_by_severity(observations)
    return (*blocking, *warnings, *advisories)


def _browser_verification_result(
    observations: Sequence[PageObservation],
    *,
    source: str,
) -> VerificationResult:
    blocking, warnings, advisories = page_findings_by_severity(observations)

    if not blocking and not warnings and not advisories:
        return VerificationResult(ok=True)

    summary = f"{source} {len(blocking)} engelleyici sorun" if blocking else ""

    return VerificationResult(
        ok=not blocking,
        summary=summary,
        findings=blocking,
        warnings=warnings,
        advisories=advisories,
    )

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


def _icons(page: PageObservation) -> list[str]:
    """Boyut verilmemiş SVG absürt büyüklükte render edilir; çok yaygın, tartışmasız bozuk.

    Ölçüt MUTLAK boyuttur: kapsayıcı içeriğe göre şiştiği için "ikon kapsayıcıdan
    büyük" kuralı hiç ateşlemiyordu — gerçek çıktıda 95px'lik kalp, 111px'lik butonun
    içindeydi ve oran testini geçiyordu.
    """
    if not page.oversized_icons:
        return []
    ornek = ", ".join(
        f"{secici} ({boy}x{en}px)" for secici, boy, en in page.oversized_icons[:MAX_ITEMS_PER_KIND]
    )
    return [
        f"{page.name} içinde {len(page.oversized_icons)} ikon devasa boyutta: {ornek}. "
        "İkonlar 16-48px olur; bu SVG'lere width/height verilmemiş, kapsayıcı da "
        "onlara göre şişmiş."
    ]


def _clipped(page: PageObservation) -> list[str]:
    """Kapsayıcıyı taşan ama KAYDIRILAMAYAN içerik kullanıcıya hiç ulaşmaz."""
    if not page.clipped:
        return []
    ornek = ", ".join(secici for secici, _, _ in page.clipped[:MAX_ITEMS_PER_KIND])
    return [
        f"{page.name} içinde {len(page.clipped)} öğe ekranın dışına taşıyor ve sayfa "
        f"yatay kaydırılamıyor — bu içeriğe erişilemiyor: {ornek}. Sarmalayan bir "
        "düzene (wrap/grid) çevir ya da kapsayıcıyı kaydırılabilir yap."
    ]


def _targets(page: PageObservation) -> list[str]:
    """WCAG 2.2 SC 2.5.8: tıklanabilir öğe en az 24x24 CSS px olmalı."""
    if not page.small_targets:
        return []
    ornek = ", ".join(
        f"{secici} ({en}x{boy})" for secici, en, boy in page.small_targets[:MAX_ITEMS_PER_KIND]
    )
    return [
        f"{page.name} içinde {len(page.small_targets)} dokunma hedefi 24x24 px'ten küçük "
        f"(WCAG 2.2 SC 2.5.8): {ornek}. Dolgu ya da min-height ekle."
    ]


def _empty(page: PageObservation) -> list[str]:
    """Başlığı olan ama içi boş bölüm — sayfa geçerli görünür, içerik yoktur.

    Gerçek hata: <script> etiketi düştüğü için JavaScript'in doldurduğu bölümlerin
    hepsi boş kaldı. Konsol tertemizdi (çalışan kod yok), HTML geçerliydi, metin
    kapısı temiz dedi. Belirtiyi doğrudan ölçmek gerekiyordu.
    """
    if not page.empty_sections:
        return []
    return [
        f"{page.name} içinde {len(page.empty_sections)} bölümün başlığı var ama içi BOŞ: "
        f"{', '.join(page.empty_sections[:MAX_ITEMS_PER_KIND])}. İçeriği üreten kod "
        "çalışmıyor ya da hiç çağrılmıyor."
    ]


def _oversized(page: PageObservation) -> list[str]:
    """Footer/header gibi yardımcı bloklar ekran boyunu aşmamalı.

    Ölçülen gerçek hata: model tüm footer bağlantı gruplarını tek div'e koydu; o
    sütun 1109px'e uzadı, footer 1237px oldu (ekranın %137'si) ve telif satırı
    ortada asılı kaldı. Devasa bir footer, yanlış DOM yapısının belirtisidir.
    """
    if not page.oversized_blocks:
        return []
    detay = ", ".join(
        f"{secici} {boy}px (ekran {ekran}px)"
        for secici, boy, ekran in page.oversized_blocks[:MAX_ITEMS_PER_KIND]
    )
    return [
        f"{page.name} içinde yardımcı blok ekran yüksekliğini aşıyor: {detay}. "
        "Muhtemelen içerik tek sütuna yığılmış — grupları ayrı grid öğesi yap ve "
        "kapsayıcıya align-items: start ver."
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
        # HTML dosyası YOKSA proje sayfayı çalışma anında üretiyor olabilir
        # (Next.js, Vite, Nuxt…). Ölçüldü: kapı tam da bu proje türünde kördü —
        # model `globals.css` değiştirip "sen kontrol et" dedi ve hiçbir şey
        # ölçülmedi. Sunucu yalnızca DÜZEN değiştiyse ayağa kaldırılır.
        if not pages:
            return await self._verify_dev_server()
        if not _playwright_available():
            return VerificationResult(ok=True)

        try:
            observations = await self._observe(pages)
        except Exception as exc:
            # Tarayıcı ikilisi indirilmemiş, sandbox izin vermemiş, uç çökmüş olabilir.
            # Doğrulama bir iyileştirmedir; turu düşürmesi kabul edilemez.
            _logger.debug("tarayıcı doğrulaması atlandı: %s", exc)
            return VerificationResult(ok=True)

        return _browser_verification_result(observations, source="tarayıcıda")

    async def _verify_dev_server(self) -> VerificationResult:
        """Dev sunucusunu ayağa kaldırıp kök sayfayı ölç; koşullar tutmazsa sessizce geç.

        Kapı üç koşul birden sağlanmazsa hiç kurulmaz: değişen dosyalar düzeni
        etkilemeli, projede `package.json` bulunmalı ve orada tanımlı bir `dev`
        betiği olmalı. Komut uydurulmaz.

        Sunucu HER durumda kapatılır ve her hata yutulur: doğrulama bir
        iyileştirmedir, turu düşürmesi kabul edilemez.
        """
        touched = sorted(self._context.touched)
        if not touched or not touches_layout(touched):
            return VerificationResult(ok=True)
        root = self._context.root
        paket = root / "package.json"
        if not paket.is_file():
            return VerificationResult(ok=True)
        try:
            komut = dev_server_command(json.loads(paket.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return VerificationResult(ok=True)
        if komut is None:
            return VerificationResult(ok=True)
        # Tarayıcı en SONDA yoklanır: ölçülecek bir şey olmadığı anlaşıldığında
        # Playwright'ı hiç içeri almamak bu kapının kuralı.
        if not _playwright_available():
            return VerificationResult(ok=True)

        try:
            observations = await self._observe_dev_server(root, komut)
        except Exception as exc:
            _logger.debug("dev sunucusu doğrulaması atlandı: %s", exc)
            return VerificationResult(ok=True)
        if observations is None:
            return VerificationResult(ok=True)

        return _browser_verification_result(
            observations,
            source="çalışan sayfada",
        )

    async def _observe_dev_server(
        self, root: Path, komut: list[str]
    ) -> list[PageObservation] | None:
        from playwright.async_api import async_playwright

        port = _free_port()
        surec = await asyncio.create_subprocess_exec(
            *komut,
            "--",
            "--port",
            str(port),
            cwd=str(root),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        adres = f"http://127.0.0.1:{port}/"
        try:
            if not await _wait_until_serving(adres):
                return None
            async with async_playwright() as driver:
                browser = await driver.chromium.launch()
                try:
                    return [await self._observe_page(browser, adres, "çalışan sayfa")]
                finally:
                    await browser.close()
        finally:
            # Sunucu HER YOLDA kapatılır: doğrulama kapısı arkasında süreç bırakamaz.
            with contextlib.suppress(ProcessLookupError):
                surec.terminate()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(surec.wait(), timeout=10)

    async def _observe(self, pages: list[Path]) -> list[PageObservation]:
        from playwright.async_api import async_playwright

        observations: list[PageObservation] = []
        async with async_playwright() as driver:
            browser = await driver.chromium.launch()
            try:
                for path in pages:
                    observations.append(
                        await self._observe_page(browser, path.as_uri(), path.name)
                    )
            finally:
                await browser.close()
        return observations

    async def _observe_page(self, browser: object, hedef: str, ad: str) -> PageObservation:
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

        # Düzen ölçümü HER genişlikte yapılır. Yalnızca en darda ölçmek yanlış bir
        # varsayımdı: gerçek çıktıda devasa ikon ve kırpılmış yorum kartı yalnızca
        # 1440px'te ortaya çıkıyordu, 375px'te kartlar alt alta dizildiği için kayboluyordu.
        layout: dict[str, list[tuple[str, int, int]]] = {
            "oversizedIcons": [],
            "clipped": [],
            "smallTargets": [],
        }
        bos_bolumler: list[str] = []
        buyuk_bloklar: list[tuple[str, int, int]] = []
        try:
            for width in VIEWPORTS:
                await page.set_viewport_size({"width": width, "height": 900})
                await page.goto(hedef, timeout=PAGE_TIMEOUT_MS, wait_until="load")
                actual = await page.evaluate("document.documentElement.scrollWidth")
                # 1px tolerans: yuvarlama farkı taşma sayılmamalı.
                if isinstance(actual, int | float) and actual > width + 1:
                    overflowing.append((width, int(actual)))

                olculen = await page.evaluate(_LAYOUT_PROBE)
                for anahtar, bulunan in layout.items():
                    bulunan.extend(_as_triples(olculen.get(anahtar)))
                ham_bos = olculen.get("emptySections")
                if isinstance(ham_bos, list):
                    bos_bolumler.extend(str(item) for item in ham_bos)
                buyuk_bloklar.extend(_as_triples(olculen.get("oversizedBlocks")))
        finally:
            await page.close()

        return PageObservation(
            name=ad,
            console_errors=tuple(console_errors),
            failed_requests=tuple(failed),
            overflowing=tuple(overflowing),
            oversized_icons=_tekil_ucluler(layout["oversizedIcons"]),
            clipped=_tekil_ucluler(layout["clipped"]),
            small_targets=_tekil_ucluler(layout["smallTargets"]),
            empty_sections=tuple(dict.fromkeys(bos_bolumler)),
            oversized_blocks=_tekil_ucluler(buyuk_bloklar),
        )


def _tekil_ucluler(rows: list[tuple[str, int, int]]) -> tuple[tuple[str, int, int], ...]:
    """Aynı öğe birden çok genişlikte ölçülür; seçiciye göre tekilleştir."""
    return tuple(dict.fromkeys(rows))


def _as_triples(rows: object) -> tuple[tuple[str, int, int], ...]:
    """Tarayıcıdan gelen ham listeyi tiplenmiş üçlülere çevir; bozuk satırı atla."""
    if not isinstance(rows, list):
        return ()
    triples: list[tuple[str, int, int]] = []
    for row in rows:
        if isinstance(row, list) and len(row) == 3:
            secici, birinci, ikinci = row
            triples.append((str(secici), int(birinci), int(ikinci)))
    return tuple(triples)


#: Sayfa içinde çalışan ölçüm. Yorum DEĞİL ölçüm döndürür; karar Python tarafında.
_LAYOUT_PROBE = """() => {
    const ad = (e) => e.tagName.toLowerCase() +
        (e.className && typeof e.className === 'string'
            ? '.' + e.className.trim().split(/\\s+/)[0] : '');

    // 1) Etkileşimli kontrol içinde ABSÜRT büyük ikon. Kapsayıcı içeriğe göre şiştiği
    //    için "ikon kapsayıcıdan büyük" kuralı hiç ateşlemez; ölçüt mutlak boyuttur.
    //    Pratikte ikonlar 16-48px'tir; 64px üstü neredeyse her zaman eksik width/height.
    const oversizedIcons = [];
    for (const kap of document.querySelectorAll('button, a')) {
        const ikon = kap.querySelector('svg, img');
        if (!ikon) continue;
        const ik = ikon.getBoundingClientRect();
        if (ik.height > 64 && kap.innerText.trim().length < 3) {
            oversizedIcons.push([ad(kap), Math.round(ik.height), Math.round(ik.width)]);
        }
    }

    // 2) Görüntü alanını taşan AMA sayfa yatay kaydırılamayan içerik: kırpılır ve
    //    kullanıcı ona hiç ulaşamaz. Sayfa kayabiliyorsa içerik erişilebilir demektir.
    const clipped = [];
    const kayabilir = document.documentElement.scrollWidth > window.innerWidth + 1;
    if (!kayabilir) {
        // position:fixed öğeler belge akışının DIŞINDADIR: kapalı çekmece, modal ve
        // toast bilinçli olarak ekran dışında park edilir. Bunları "erişilemeyen
        // içerik" saymak yanlış pozitiftir — gerçek bir koşuda mini sepet böyle
        // bildirildi.
        const akisDisi = (e) => {
            for (let n = e; n && n !== document.body; n = n.parentElement) {
                if (getComputedStyle(n).position === 'fixed') return true;
            }
            return false;
        };
        const tasiyor = (e) => {
            if (akisDisi(e)) return false;
            const r = e.getBoundingClientRect();
            return r.width > 0 && r.right > window.innerWidth + 4;
        };
        for (const e of document.querySelectorAll('section *, main *')) {
            // Yalnızca EN DIŞTAKİ taşan öğe bildirilir: bir kart taşıyorsa içindeki
            // her başlık ve paragraf da taşar ve 58 satırlık gürültü üretirdi.
            if (!tasiyor(e) || (e.parentElement && tasiyor(e.parentElement))) continue;
            clipped.push([ad(e), Math.round(window.innerWidth),
                          Math.round(e.getBoundingClientRect().right)]);
        }
    }

    // 3) WCAG 2.2 SC 2.5.8 — tıklanabilir öğe en az 24x24 CSS px.
    const smallTargets = [];
    for (const e of document.querySelectorAll('a[href], button, input, select')) {
        const r = e.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        if (r.width < 24 || r.height < 24) {
            smallTargets.push([ad(e), Math.round(r.width), Math.round(r.height)]);
        }
    }

    // 4) Başlığı olan ama içi boş bölüm. İçerik JavaScript'le geliyorsa ve JS
    //    çalışmıyorsa sayfa geçerli görünür ama boştur.
    const emptySections = [];
    for (const s of document.querySelectorAll('section, [id]')) {
        const baslik = s.querySelector('h1, h2, h3');
        if (!baslik || !s.id) continue;
        const govde = s.innerText.replace(baslik.innerText, '').trim();
        const ogeler = s.querySelectorAll('img, a, button, input, li, p').length;
        if (govde.length < 20 && ogeler === 0) emptySections.push('#' + s.id);
    }

    // 5) Ekran boyunu aşan yardımcı blok. Footer/header bir sayfa kadar uzunsa
    //    içerik tek sütuna yığılmış demektir.
    const oversizedBlocks = [];
    for (const e of document.querySelectorAll('footer, header')) {
        const y = Math.round(e.getBoundingClientRect().height);
        if (y > window.innerHeight) {
            oversizedBlocks.push([e.tagName.toLowerCase(), y, window.innerHeight]);
        }
    }

    return {oversizedIcons, clipped, smallTargets, emptySections, oversizedBlocks};
}"""

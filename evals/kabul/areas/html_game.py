"""Kabul alanı `html_oyun`: tarayıcıda oynanan 2D oyun (`index.html`).

Denetçi oyunu yerel sunucuda headless chromium ile açar ve bağımsız ölçer: konsol
hatası, canvas/oyun alanının boş olmaması, `requestAnimationFrame` döngüsü, tuşlara
tepki (tuşsuz bekleme ile karşılaştırarak), skor/can HUD'ı ve yeniden başlatma.
Ölçülemeyen madde geçirilmez; ayrıntıda neden yazılır.

Aşağıdaki eşikler BAŞLANGIÇ eşikleridir; taban ölçümüyle sabitlenecek.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from evals.kabul.areas._browser import (
    BrowserUnavailableError,
    OpenedPage,
    PageInteractionError,
    navigate,
    open_page,
)
from evals.kabul.areas._game_probe import (
    INIT_SCRIPT,
    KEY_HOLD_MS,
    KEY_SEQUENCE,
    HudReading,
    find_game_area,
    hold_key,
    make_shooter,
    motion_energy,
    raf_count,
    read_hud,
)
from evals.kabul.areas._pixels import luminance_variance
from evals.kabul.model import Area, Check, Inspection

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

#: Ajana verilen görev.
TASK = (
    "Tarayıcıda oynanan, BASİT OLMAYAN 2D bir aksiyon oyunu yap: yukarıdan bakışlı bir "
    "hayatta kalma/nişancı oyunu. Tek bir klasörde `index.html` ile açılsın (yanında "
    "css/js dosyaları olabilir). Oyuncu ok tuşlarıyla hareket etsin, boşluk tuşu ateş "
    "etsin. En az 3 bölüm (dalga) olsun ve zorluk artsın; en az 3 farklı düşman türü "
    "(ör. oyuncuyu kovalayan, uzaktan ateş eden, bölünen) ve son bölümde bir boss "
    "bulunsun. Toplanacak güçlendirmeler (can, hızlı ateş vb.), skor, can ve bölüm "
    "göstergesi, P tuşuyla duraklatma, en yüksek skorun localStorage'da saklanması ve "
    "çarpışma/patlama efektleri olsun. Can bitince oyun bitti ekranı gelsin ve oyun R "
    "tuşuyla ya da düğmeyle yeniden başlatılabilsin. Oyun uzun oynandığında donmasın ve "
    "konsolda hata vermesin. Oyun GÖRSEL VARLIKLARLA (asset) yapılsın ve bu varlıkları "
    "SEN üret: `assets/` klasöründe oyuncu, her düşman türü, boss, güçlendirmeler, mermi, "
    "patlama ve zemin için ayrı görsel dosyaları (SVG ya da PNG; en az 8 dosya) oluştur ve "
    "oyunda bu dosyaları yükleyip çiz. Basit kare/daire çizimi değil, tutarlı bir görsel "
    "stile sahip, oyunu çekici gösteren sprite'lar olsun. Oyun alanı ekranın tamamını "
    "kaplasın, her karede ekran temizlensin, skor/can yazısı okunaklı olsun. Oyun "
    "`index.html` dosyasına çift tıklanarak (file://) açıldığında da çalışsın."
)
TIMEOUT_S = 3600.0
#: Sayfa yüklendikten sonra ilk ölçüme dek bekleme (ms): açılış ekranı oturur.
LOAD_SETTLE_MS = 800
#: Oyun alanının "boş değil" sayılması için parlaklık varyansı alt sınırı. Küçük
#: sprite'lı koyu zemin bile yüzlerce verir; düz tek renk sıfırdır.
MIN_AREA_VARIANCE = 4.0
#: rAF döngüsü ölçüm penceresi (ms) ve bu pencerede en az çağrı (60 fps'te ~60; başsız
#: tarayıcı kısıtlamasına pay bırakıp üçte birine indirildi).
RAF_WINDOW_MS = 1000
MIN_RAF_CALLS = 20
#: rAF yoksa (setInterval oyunu) tuşsuz beklemedeki hareketin kabul eşiği.
MIN_IDLE_MOTION = 0.005
#: Tuşlu hareket enerjisinin tuşsuzdan en az bu kadar fazla olması gerekir.
KEY_ENERGY_MARGIN = 0.01
#: Yeniden başlat ölçümünde oynama: tur sayısı ve tuş basış süresi (ms).
PLAY_ROUNDS = 6
PLAY_HOLD_MS = 400
#: Yeniden başlat sonrası durumun oturma süresi (ms).
RESTART_SETTLE_MS = 700
#: Oyun ortasında R sıfırlamazsa oyunun kendiliğinden bitmesi için beklenen üst sınır.
#: Ölçüldü (4 Ekim): örnek oyunda R yalnız "oyun bitti" ekranında çalışıyordu (geçerli
#: tasarım); denetçi R'ye oyun ortasında bastığı için çalışan oyunu "kaldı" saydı.
GAME_OVER_WAIT_MS = 90_000
GAME_OVER_POLL_MS = 500
_END_STATE_JS = """() => { try { const s = typeof window.__GAME_STATE__ === 'function'
  ? window.__GAME_STATE__() : null; const d = s && (s.durum ?? s.state ?? s.mode);
  return typeof d === 'string' && /over|bitti|bit|son|dead|lost|kaybet/i.test(d);
  } catch (e) { return false; } }"""
_MOVE_KEYS = KEY_SEQUENCE[:4]
_RESTART_TEXT = re.compile(r"yeniden|restart|tekrar|again|replay|baştan|retry", re.IGNORECASE)

CHECK_NAMES = (
    "index.html var",
    "konsol hatası 0",
    "oyun alanı var ve boş değil",
    "requestAnimationFrame döngüsü çalışıyor",
    "ok tuşları + boşluk oyunu değiştiriyor",
    "skor/can HUD'ı var",
    "yeniden başlat durumu sıfırlıyor",
    "uzun oyunda donmuyor",
    "kendi ürettiği görsel varlıklar yükleniyor",
    "ekranda bariz görsel kusur yok",
)
#: Ajanın kendisinin üretmesi beklenen görsel dosya sayısı (assets/ altında).
MIN_ASSET_FILES = 8
_ASSET_SUFFIXES = frozenset({".svg", ".png", ".webp", ".jpg", ".jpeg", ".gif"})
#: Sayfanın başarıyla yüklediği görsel kaynak adları (performance kayıtları + <img>).
_LOADED_IMAGES_JS = """() => [...new Set([
  ...performance.getEntriesByType('resource').map((e) => e.name),
  ...[...document.images].filter((i) => i.complete && i.naturalWidth > 0).map((i) => i.src),
].map((u) => decodeURIComponent(u.split('?')[0]).split('/').pop()))]"""
#: Donma ölçümü için rastgele tuşlarla oynanan süre (ms). Kullanıcı (6 Ekim 2026):
#: "oyun bir anda duruyor" — kısa ölçümlerde görünmeyen, oynadıkça çöken döngü.
LONG_PLAY_MS = 30_000
#: Uzun oyundan sonra 1 sn'de en az bu kadar rAF çağrısı: döngü hâlâ dönüyor.
MIN_LONG_PLAY_RAF = 20


@dataclass(frozen=True, slots=True)
class RestartProbe:
    """Yeniden başlat ölçümü: oyun öncesi, oynadıktan sonra ve yeniden başlattıktan sonra HUD."""

    initial: tuple[str, ...]
    played: tuple[str, ...]
    restarted: tuple[str, ...]
    trigger: str


@dataclass(frozen=True, slots=True)
class GameReport:
    """Tarayıcıda ölçülen değerler."""

    console_errors: tuple[str, ...]
    has_area: bool
    area_variance: float
    raf_calls: int
    idle_energy: float
    key_energy: float
    hud: HudReading
    restart: RestartProbe
    #: Durum kancası oyuncu konumu veriyorsa tuşlarla yer değiştirdi mi (None: ölçülemedi).
    player_moved: bool | None = None
    #: Uzun rastgele oyundan sonra 1 sn'deki rAF çağrısı ve o sırada çıkan konsol hataları.
    long_play_raf: int = MIN_LONG_PLAY_RAF
    long_play_errors: tuple[str, ...] = ()
    #: Oyun açılıp oynanırken başarıyla yüklenen görsel dosya adları.
    loaded_images: tuple[str, ...] = ()


#: Açılış menüsündeki görünür "Başla/Start/Play" düğmesine bas (oyuncu da basar).
#: Ölçüldü (dalga24): oyun "Başla" düğmesiyle açılıyordu; denetçi yalnız tuşa bastığı
#: için menüde kaldı ve çalışan oyunu "tuşlar etkisiz" saydı.
_START_JS = """() => { const re = /ba[sş]la|start|play|oyna/i;
  const shown = (el) => { const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    for (let e = el; e; e = e.parentElement) { const s = getComputedStyle(e);
      if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) < 0.05 ||
          s.pointerEvents === 'none') return false; } return true; };
  const b = [...document.querySelectorAll('button, [role=button], a, input[type=button]')]
    .find((el) => re.test(el.innerText || el.value || '') && shown(el));
  if (b) { b.click(); return (b.innerText || b.value || '').trim().slice(0, 30); } return null; }"""


def _fresh_load(opened: OpenedPage) -> None:
    """Sayfayı (yeniden) aç, açılış ekranı oturunca varsa başlat düğmesine bas."""
    navigate(opened)
    opened.page.wait_for_timeout(LOAD_SETTLE_MS)
    if opened.page.evaluate(_START_JS):
        opened.page.wait_for_timeout(LOAD_SETTLE_MS)


def _play(page: Page) -> None:
    """Boşluk ve ok tuşlarıyla bir süre oyna (skor/can değişsin)."""
    hold_key(page, "Space", PLAY_HOLD_MS)
    for _ in range(PLAY_ROUNDS):
        for key in _MOVE_KEYS:
            hold_key(page, key, PLAY_HOLD_MS)


#: Öğe ve atalarından biri saydam (opacity≈0) ya da tıklamaya kapalıysa oyuncu onu görmez.
#: Ölçüldü (dalga23): gizli "oyun bitti" katmanı `opacity:0; pointer-events:none` idi;
#: Playwright `is_visible()` onu görünür saydı, tıklama 15 sn bekleyip oyunun TÜM
#: ölçümlerini düşürdü — oyunda kusur yoktu.
_REALLY_SHOWN_JS = """(el) => { for (let e = el; e; e = e.parentElement) {
  const s = getComputedStyle(e);
  if (parseFloat(s.opacity) < 0.05 || s.pointerEvents === 'none' ||
      s.visibility === 'hidden' || s.display === 'none') return false; }
  return true; }"""


def _shown_button(page: Page) -> Locator | None:
    button = page.get_by_role("button", name=_RESTART_TEXT)
    if button.count() == 0 or not button.first.is_visible():
        return None
    return button.first if button.first.evaluate(_REALLY_SHOWN_JS) else None


def _trigger_restart(page: Page) -> str:
    """R tuşuna bas; 'yeniden başlat' benzeri gerçekten görünen bir düğme varsa ona da tıkla."""
    page.keyboard.press("r")
    page.keyboard.press("R")
    button = _shown_button(page)
    if button is not None:
        button.click()
        return "R tuşu + düğme"
    return "R tuşu"


def _wait_for_game_over(page: Page) -> bool:
    """Oyun bitene dek bekle: durum kancası bitiş der ya da yeniden başlat düğmesi görünür."""
    for _ in range(GAME_OVER_WAIT_MS // GAME_OVER_POLL_MS):
        if page.evaluate(_END_STATE_JS) or _shown_button(page) is not None:
            return True
        page.wait_for_timeout(GAME_OVER_POLL_MS)
    return False


def _restart_probe(opened: OpenedPage) -> RestartProbe:
    _fresh_load(opened)
    page = opened.page
    initial = read_hud(page).lines
    _play(page)
    played = read_hud(page).lines
    trigger = _trigger_restart(page)
    page.wait_for_timeout(RESTART_SETTLE_MS)
    restarted = read_hud(page).lines
    if restarted != initial and _wait_for_game_over(page):
        trigger = "oyun bittikten sonra " + _trigger_restart(page)
        page.wait_for_timeout(RESTART_SETTLE_MS)
        restarted = read_hud(page).lines
    return RestartProbe(initial, played, restarted, trigger)


def measure(root: Path) -> GameReport:
    """Oyunu aç; tüm ölçümleri tek oturumda yap."""
    with open_page(root, init_script=INIT_SCRIPT) as opened:
        page = opened.page
        _fresh_load(opened)
        area = find_game_area(page)
        shoot = make_shooter(page, area)
        variance = luminance_variance(shoot())
        before = raf_count(page)
        page.wait_for_timeout(RAF_WINDOW_MS)
        raf_calls = raf_count(page) - before
        idle = motion_energy(page, shoot, press_keys=False)
        hud = read_hud(page)
        _fresh_load(opened)
        keyed = motion_energy(page, shoot, press_keys=True)
        # Ok tuşları sağ-yukarı-sol-aşağı sırasıyla basılınca oyuncu başladığı yere döner;
        # konum tek yönlü (sağ) basışın öncesi ve sonrasıyla ölçülür.
        konum_once = page.evaluate(_PLAYER_POS_JS)
        hold_key(page, "ArrowRight", KEY_HOLD_MS)
        konum_sonra = page.evaluate(_PLAYER_POS_JS)
        restart = _restart_probe(opened)
        long_raf, long_errors = _long_play(opened)
        loaded = tuple(opened.page.evaluate(_LOADED_IMAGES_JS))
        return GameReport(
            console_errors=opened.console.errors,
            has_area=area is not None,
            area_variance=variance,
            raf_calls=raf_calls,
            idle_energy=idle,
            key_energy=keyed,
            player_moved=_moved(konum_once, konum_sonra),
            hud=hud,
            restart=restart,
            long_play_raf=long_raf,
            long_play_errors=long_errors,
            loaded_images=loaded,
        )


def _long_play(opened: OpenedPage) -> tuple[int, tuple[str, ...]]:
    """Oyunu baştan aç, LONG_PLAY_MS boyunca tuşlarla oyna; döngü hâlâ dönüyor mu?"""
    _fresh_load(opened)
    page = opened.page
    onceki = len(opened.console.errors)
    tuslar = (*_MOVE_KEYS, "Space")
    for adim in range(LONG_PLAY_MS // PLAY_HOLD_MS):
        hold_key(page, tuslar[adim % len(tuslar)], PLAY_HOLD_MS)
    before = raf_count(page)
    page.wait_for_timeout(RAF_WINDOW_MS)
    return raf_count(page) - before, tuple(opened.console.errors[onceki:])


def _long_play_check(report: GameReport) -> Check:
    hatalar = report.long_play_errors
    ok = report.long_play_raf >= MIN_LONG_PLAY_RAF and not hatalar
    return Check(
        CHECK_NAMES[7],
        ok,
        f"{LONG_PLAY_MS // 1000} sn oyundan sonra {report.long_play_raf} rAF/sn "
        f"(eşik {MIN_LONG_PLAY_RAF}); oyun sırasında {len(hatalar)} konsol hatası"
        + (f": {hatalar[0][:120]}" if hatalar else ""),
    )


def _area_check(report: GameReport) -> Check:
    name = CHECK_NAMES[2]
    if not report.has_area:
        return Check(name, False, "canvas ya da oyun alanı öğesi bulunamadı")
    return Check(
        name,
        report.area_variance >= MIN_AREA_VARIANCE,
        f"parlaklık varyansı {report.area_variance:.1f} (eşik {MIN_AREA_VARIANCE:g})",
    )


def _raf_check(report: GameReport) -> Check:
    alive = report.raf_calls >= MIN_RAF_CALLS or report.idle_energy >= MIN_IDLE_MOTION
    return Check(
        CHECK_NAMES[3],
        alive,
        f"{RAF_WINDOW_MS} ms'de {report.raf_calls} rAF çağrısı (eşik {MIN_RAF_CALLS}); "
        f"tuşsuz hareket enerjisi {report.idle_energy:.4f} (eşik {MIN_IDLE_MOTION})",
    )


#: Durum kancasındaki oyuncu konumu: {oyuncu|player: {x, y}} ya da üst düzey x/y.
_PLAYER_POS_JS = """() => { try { const s = typeof window.__GAME_STATE__ === 'function'
  ? window.__GAME_STATE__() : null; const p = s && (s.oyuncu || s.player);
  return p && typeof p.x === 'number' && typeof p.y === 'number' ? [p.x, p.y] : null;
  } catch (e) { return null; } }"""
#: Bundan az yer değişimi hareket sayılmaz (px).
MIN_PLAYER_MOVE = 8


def _moved(once: object, sonra: object) -> bool | None:
    if not (isinstance(once, list) and isinstance(sonra, list)):
        return None
    return abs(sonra[0] - once[0]) + abs(sonra[1] - once[1]) >= MIN_PLAYER_MOVE


def _key_check(report: GameReport) -> Check:
    gain = report.key_energy - report.idle_energy
    # Kalabalık oyunda düşmanlar ekranı zaten çok değiştirir; tuş etkisi piksel farkında
    # kaybolur. Ölçüldü (8 Ekim, dalga41): oyuncu 640→1098 px gitti ama fark 0,0073 < 0,01
    # çıktı. Durum kancası konum veriyorsa asıl kanıt konumdur.
    if report.player_moved is not None:
        return Check(
            CHECK_NAMES[4],
            report.player_moved,
            f"durum kancasında oyuncu konumu tuşlarla "
            f"{'değişti' if report.player_moved else 'DEĞİŞMEDİ'}; piksel farkı {gain:.4f}",
        )
    return Check(
        CHECK_NAMES[4],
        gain >= KEY_ENERGY_MARGIN,
        f"tuşlu enerji {report.key_energy:.4f}, tuşsuz {report.idle_energy:.4f}, "
        f"fark {gain:.4f} (eşik {KEY_ENERGY_MARGIN})",
    )


def _hud_check(report: GameReport) -> Check:
    hud = report.hud
    if hud.found:
        return Check(
            CHECK_NAMES[5],
            True,
            f"DOM: {list(hud.dom)[:3]}; canvas'a çizilen: {list(hud.canvas)[:3]}; "
            f"__GAME_STATE__: {list(hud.state)[:3]}",
        )
    return Check(
        CHECK_NAMES[5],
        False,
        "ölçülemedi: DOM metninde ve canvas fillText çağrılarında skor/can metni yok "
        "(HUD sprite/görsel olarak çiziliyor olabilir)",
    )


def _restart_check(report: GameReport) -> Check:
    probe = report.restart
    name = CHECK_NAMES[6]
    if not probe.initial:
        return Check(name, False, "ölçülemedi: başlangıçta HUD metni okunamadı")
    if probe.played == probe.initial:
        return Check(
            name,
            False,
            f"ölçülemedi: oynarken HUD değişmedi ({list(probe.initial)[:3]}); sıfırlanma izlenemez",
        )
    reset = probe.restarted == probe.initial
    return Check(
        name,
        reset,
        f"tetik: {probe.trigger}; başlangıç {list(probe.initial)[:3]}, oyun sonrası "
        f"{list(probe.played)[:3]}, yeniden başlatma sonrası {list(probe.restarted)[:3]}",
    )


def _asset_check(workdir: Path, report: GameReport) -> Check:
    """assets/ altında ajanın ürettiği görseller var ve oyun onları gerçekten yüklüyor.

    Kullanıcı isteği (6 Ekim 2026): "assetli bir oyun olsun, asset'i bile yapsın".
    """
    klasor = workdir / "assets"
    dosyalar = (
        sorted(p.name for p in klasor.rglob("*") if p.suffix.lower() in _ASSET_SUFFIXES)
        if klasor.is_dir()
        else []
    )
    yuklenen = [ad for ad in dosyalar if ad in set(report.loaded_images)]
    return Check(
        CHECK_NAMES[8],
        len(yuklenen) >= MIN_ASSET_FILES,
        f"assets/ altında {len(dosyalar)} görsel, oyunda yüklenen {len(yuklenen)} "
        f"(eşik {MIN_ASSET_FILES}): {', '.join(yuklenen[:6])}",
    )


def _visual_check(workdir: Path) -> Check:
    """Oyunu kullanıcı gibi dosyadan aç, ekran görüntüsünden bariz kusurları ölç.

    Ölçüldü (6 Ekim 2026, dalga24): denetçi 7/8 verdi; görüntüde oyun alanı ekranın bir
    çeyreğiydi ve oyuncu iz bırakıyordu. Kullanıcı "rezalet" dedi. Ölçüm Fusion'ın kendi
    oyun sondasıyla aynıdır (`fusion_cli.tools.game_visual`).
    """
    import asyncio

    from fusion_cli.tools.play_probe import probe_game

    try:
        rapor = asyncio.run(probe_game((workdir / "index.html").as_uri()))
    except Exception as error:  # sınır: tarayıcı açılamadı
        return Check(CHECK_NAMES[9], False, f"görsel ölçüm yapılamadı: {str(error)[:120]}")
    # ölçüldü (dalga44): durum 'playing' oldu ama menü katmanı ekranı örtmeye devam etti
    sorunlar = (*rapor.startup_problems, *rapor.visual_problems)
    if rapor.asset_usage.problem:  # ölçüldü (dalga41): sprite yüklendi, düşman daire çizildi
        sorunlar = (*sorunlar, rapor.asset_usage.problem)
    if rapor.console_errors and not sorunlar:
        sorunlar = (f"dosyadan açılınca konsol hatası: {rapor.console_errors[0][:120]}",)
    return Check(CHECK_NAMES[9], not sorunlar, "; ".join(sorunlar) or "kusur ölçülmedi")


def _report_checks(report: GameReport) -> tuple[Check, ...]:
    errors = report.console_errors
    console = Check(
        CHECK_NAMES[1],
        not errors,
        f"{len(errors)} konsol hatası" + (f": {errors[0][:120]}" if errors else ""),
    )
    return (
        console,
        _area_check(report),
        _raf_check(report),
        _key_check(report),
        _hud_check(report),
        _restart_check(report),
        _long_play_check(report),
    )


def inspect(workdir: Path, values: Mapping[str, str]) -> Inspection:
    """Ajanın oyununu bağımsız ölç."""
    if not (workdir / "index.html").is_file():
        reason = "index.html yok (ajan çıktı üretmedi)"
        return Inspection(checks=tuple(Check(name, False, reason) for name in CHECK_NAMES))
    present = Check(CHECK_NAMES[0], True, "index.html bulundu")
    try:
        report = measure(workdir)
    except BrowserUnavailableError as error:
        return Inspection(invalid_reason=str(error))
    except PageInteractionError as error:
        reason = f"oyun ölçülemedi: {str(error)[:160]}"
        return Inspection(checks=(present, *(Check(n, False, reason) for n in CHECK_NAMES[1:])))
    return Inspection(
        checks=(
            present,
            *_report_checks(report),
            _asset_check(workdir, report),
            _visual_check(workdir),
        )
    )


AREA = Area(name="html_oyun", task=TASK, timeout_s=TIMEOUT_S, inspect=inspect)

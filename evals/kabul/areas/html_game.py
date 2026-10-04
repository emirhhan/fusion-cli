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
    from playwright.sync_api import Page

#: Ajana verilen görev.
TASK = (
    "Tarayıcıda oynanan 2D bir oyun yap. Tek bir klasörde `index.html` ile açılsın "
    "(yanında css/js dosyaları olabilir). Oyuncu ok tuşlarıyla hareket etsin, boşluk tuşu "
    "bir eylem yapsın; toplanacak nesneler, düşmanlar, skor ve can göstergesi olsun. "
    "Can bitince oyun bitti ekranı gelsin ve oyun yeniden başlatılabilsin. Görseller "
    "için ücretsiz/lisanslı varlıklar ya da kendi ürettiğin görseller kullanılabilir."
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
)


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


def _fresh_load(opened: OpenedPage) -> None:
    """Sayfayı (yeniden) aç ve açılış ekranının oturmasını bekle."""
    navigate(opened)
    opened.page.wait_for_timeout(LOAD_SETTLE_MS)


def _play(page: Page) -> None:
    """Boşluk ve ok tuşlarıyla bir süre oyna (skor/can değişsin)."""
    hold_key(page, "Space", PLAY_HOLD_MS)
    for _ in range(PLAY_ROUNDS):
        for key in _MOVE_KEYS:
            hold_key(page, key, PLAY_HOLD_MS)


def _trigger_restart(page: Page) -> str:
    """R tuşuna bas; 'yeniden başlat' benzeri görünür bir düğme varsa ona da tıkla."""
    page.keyboard.press("r")
    page.keyboard.press("R")
    button = page.get_by_role("button", name=_RESTART_TEXT)
    if button.count() > 0 and button.first.is_visible():
        button.first.click()
        return "R tuşu + düğme"
    return "R tuşu"


def _wait_for_game_over(page: Page) -> bool:
    """Oyun bitene dek bekle: durum kancası bitiş der ya da yeniden başlat düğmesi görünür."""
    button = page.get_by_role("button", name=_RESTART_TEXT)
    for _ in range(GAME_OVER_WAIT_MS // GAME_OVER_POLL_MS):
        if page.evaluate(_END_STATE_JS) or (button.count() > 0 and button.first.is_visible()):
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
        restart = _restart_probe(opened)
        return GameReport(
            console_errors=opened.console.errors,
            has_area=area is not None,
            area_variance=variance,
            raf_calls=raf_calls,
            idle_energy=idle,
            key_energy=keyed,
            hud=hud,
            restart=restart,
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


def _key_check(report: GameReport) -> Check:
    gain = report.key_energy - report.idle_energy
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
    return Inspection(checks=(present, *_report_checks(report)))


AREA = Area(name="html_oyun", task=TASK, timeout_s=TIMEOUT_S, inspect=inspect)

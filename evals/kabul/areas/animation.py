"""Kabul alanı `animasyon`: kahve markası için animasyonlu tek sayfalık tanıtım sayfası.

Denetçi sayfayı yerel sunucuda headless chromium ile açar ve ajanın söylediğinden
bağımsız ölçer: hareket (piksel farkı), kaydırmayla beliren öğeler, CSS hareket
kalıpları, layout animasyonu ihlali, `prefers-reduced-motion` ve easing çeşitliliği.

Aşağıdaki eşikler BAŞLANGIÇ eşikleridir; taban ölçümüyle sabitlenecek.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from evals.kabul.areas import _motion_lint as lint
from evals.kabul.areas._browser import (
    BrowserUnavailableError,
    PageInteractionError,
    navigate,
    open_page,
)
from evals.kabul.areas._pixels import changed_pixel_ratio
from evals.kabul.areas._sources import Sources, collect_sources
from evals.kabul.model import Area, Check, Inspection

if TYPE_CHECKING:
    from playwright.sync_api import Page

#: Ajana verilen görev (ölçütler söylenmez; yalnız kalite beklentisi).
TASK = (
    "Bir kahve markası için animasyonlu, tek sayfalık bir tanıtım sayfası yap. Çıktı "
    "çalışma klasöründe `index.html` olsun (istersen yanında css ve js dosyaları da "
    "olabilir). Sayfada hero bölümünde bir giriş animasyonu, aşağı kaydırdıkça ortaya "
    "çıkan bölümler ve etkileşimli öğelerde hover durumları bulunsun. Beklenen kalite "
    "düzeyi Claude Opus düzeyidir: özenli tipografi, tutarlı renk paleti ve akıcı hareket."
)

#: Görev süresi tavanı (sn).
TIMEOUT_S = 3600.0
#: Ekran görüntüsü anları (ms); hero giriş animasyonu bu pencerede yakalanır.
SAMPLE_OFFSETS_MS = (0, 700, 1600)
#: Herhangi iki kare arasında değişen piksel oranının alt sınırı. %0,5: büyük bir başlığın
#: belirmesi bunu aşar, statik sayfada oran sıfırdır.
MIN_MOTION_RATIO = 0.005
#: Kaydırmayla görünümü (opacity/transform vb.) değişen öğe sayısının alt sınırı.
MIN_REVEALED_ELEMENTS = 3
#: Hareket kalıbı alt sınırı: benzersiz @keyframes + transition kalemleri + canlı animasyon.
MIN_MOTION_PATTERNS = 5
#: Farklı easing alt sınırı (tek eğri her şeyi aynı hissettirir).
MIN_EASINGS = 2
#: Kaydırma adımı bekleme süresi (ms) ve en çok adım sayısı.
SCROLL_STEP_MS = 250
MAX_SCROLL_STEPS = 40
#: Kaydırma sonrası oturma süresi (ms) ve ilk anlık görüntüler arası süre (ms).
SETTLE_MS = 600
STABILITY_GAP_MS = 200
#: Bir anlık görüntüde incelenecek en çok öğe.
MAX_SNAPSHOT_ELEMENTS = 1500

_SNAPSHOT_JS = (
    "(limit) => Array.from(document.querySelectorAll('body *')).slice(0, limit).map("
    "el => { const s = getComputedStyle(el); "
    "return [s.opacity, s.transform, s.visibility, s.clipPath, s.filter].join('|'); })"
)
_LIVE_ANIMATIONS_JS = "document.getAnimations().length"
_SCROLL_HEIGHT_JS = "document.documentElement.scrollHeight"
_INNER_HEIGHT_JS = "window.innerHeight"
_SCROLL_TO_JS = "(y) => window.scrollTo({top: y, behavior: 'instant'})"


@dataclass(frozen=True, slots=True)
class RuntimeReport:
    """Tarayıcıda ölçülen değerler."""

    console_errors: tuple[str, ...]
    motion_ratio: float
    stable_elements: int
    revealed_elements: int
    scrollable: bool
    max_live_animations: int


def _live_animations(page: Page) -> int:
    return int(page.evaluate(_LIVE_ANIMATIONS_JS))


def _sample_frames(page: Page, started: float) -> tuple[list[bytes], int]:
    """Her `SAMPLE_OFFSETS_MS` anında ekran görüntüsü al; canlı animasyon sayısını izle."""
    frames: list[bytes] = []
    live = 0
    for offset in SAMPLE_OFFSETS_MS:
        remaining = started + offset / 1000 - time.monotonic()
        if remaining > 0:
            page.wait_for_timeout(remaining * 1000)
        live = max(live, _live_animations(page))
        frames.append(page.screenshot(type="png"))
    return frames, live


def _motion_ratio(frames: list[bytes]) -> float:
    ratios = [
        changed_pixel_ratio(frames[first], frames[second])
        for first in range(len(frames))
        for second in range(first + 1, len(frames))
    ]
    return max(ratios, default=0.0)


def _snapshot(page: Page) -> list[str]:
    return cast("list[str]", page.evaluate(_SNAPSHOT_JS, MAX_SNAPSHOT_ELEMENTS))


def _scroll_through(page: Page) -> tuple[bool, int]:
    """Sayfayı adım adım sonuna kaydır; (kaydırılabilir mi, görülen en çok canlı animasyon)."""
    total = int(page.evaluate(_SCROLL_HEIGHT_JS))
    viewport = int(page.evaluate(_INNER_HEIGHT_JS))
    if total <= viewport:
        return False, 0
    live = 0
    steps = min(MAX_SCROLL_STEPS, math.ceil(total / viewport))
    for step in range(1, steps + 1):
        page.evaluate(_SCROLL_TO_JS, min(step * viewport, total))
        page.wait_for_timeout(SCROLL_STEP_MS)
        live = max(live, _live_animations(page))
    page.wait_for_timeout(SETTLE_MS)
    return True, live


def _count_revealed(
    before: list[str], stable_reference: list[str], after: list[str]
) -> tuple[int, int]:
    """(kararlı öğe sayısı, kaydırmayla değişen kararlı öğe sayısı)."""
    stable = [
        i
        for i in range(min(len(before), len(stable_reference)))
        if (before[i] == stable_reference[i])
    ]
    revealed = sum(1 for i in stable if i < len(after) and after[i] != before[i])
    return len(stable), revealed


def measure_runtime(root: Path) -> RuntimeReport:
    """Sayfayı aç; hareket, kaydırma etkisi ve konsol hatalarını ölç."""
    with open_page(root) as opened:
        page = opened.page
        started = time.monotonic()
        navigate(opened)
        frames, live = _sample_frames(page, started)
        before = _snapshot(page)
        page.wait_for_timeout(STABILITY_GAP_MS)
        stable_reference = _snapshot(page)
        scrollable, scroll_live = _scroll_through(page)
        after = _snapshot(page)
        stable, revealed = _count_revealed(before, stable_reference, after)
        return RuntimeReport(
            console_errors=opened.console.errors,
            motion_ratio=_motion_ratio(frames),
            stable_elements=stable,
            revealed_elements=revealed,
            scrollable=scrollable,
            max_live_animations=max(live, scroll_live),
        )


def _runtime_checks(report: RuntimeReport) -> tuple[Check, Check, Check]:
    errors = report.console_errors
    console = Check(
        "konsol hatası 0",
        not errors,
        f"{len(errors)} konsol hatası" + (f": {errors[0][:120]}" if errors else ""),
    )
    motion = Check(
        "t=0/700/1600 ms kareleri arasında hareket var",
        report.motion_ratio >= MIN_MOTION_RATIO,
        f"en büyük değişen piksel oranı {report.motion_ratio:.4f} (eşik {MIN_MOTION_RATIO})",
    )
    if report.scrollable:
        detail = (
            f"{report.revealed_elements} öğe kaydırmayla değişti, "
            f"{report.stable_elements} kararlı öğe içinden (eşik {MIN_REVEALED_ELEMENTS})"
        )
    else:
        detail = "sayfa kaydırılamıyor (içerik pencereden uzun değil)"
    reveal = Check(
        "kaydırınca yeni öğeler görünür hale gelir",
        report.scrollable and report.revealed_elements >= MIN_REVEALED_ELEMENTS,
        detail,
    )
    return console, motion, reveal


def _source_checks(
    sources: Sources, css: lint.CssMotion, live_animations: int
) -> tuple[Check, Check, Check, Check]:
    total = css.pattern_count + live_animations
    patterns = Check(
        f"hareket kalıbı >= {MIN_MOTION_PATTERNS}",
        total >= MIN_MOTION_PATTERNS,
        f"{len(css.keyframe_names)} @keyframes + {css.transition_count} transition kalemi + "
        f"{live_animations} canlı animasyon = {total}",
    )
    layout = Check(
        "layout özellikleri animasyon/transition'da kullanılmıyor",
        not css.layout_hits,
        f"{len(css.layout_hits)} ihlal"
        + (f": {', '.join(css.layout_hits[:5])}" if css.layout_hits else ""),
    )
    reduced = Check(
        "prefers-reduced-motion sorgusu var",
        lint.has_reduced_motion_query(sources.everything),
        "sorgu bulundu" if lint.has_reduced_motion_query(sources.everything) else "sorgu yok",
    )
    easings = sorted({*css.easings, *lint.js_easings(sources.js)})
    variety = Check(
        f">= {MIN_EASINGS} farklı easing",
        len(easings) >= MIN_EASINGS,
        f"{len(easings)} farklı easing: {', '.join(easings[:6]) or '-'}",
    )
    return patterns, layout, reduced, variety


def _failed_runtime(reason: str) -> tuple[Check, ...]:
    names = (
        "konsol hatası 0",
        "t=0/700/1600 ms kareleri arasında hareket var",
        "kaydırınca yeni öğeler görünür hale gelir",
    )
    return tuple(Check(name, False, reason) for name in names)


def _missing_output_checks() -> tuple[Check, ...]:
    reason = "index.html yok (ajan çıktı üretmedi)"
    names = (
        "konsol hatası 0",
        "t=0/700/1600 ms kareleri arasında hareket var",
        "kaydırınca yeni öğeler görünür hale gelir",
        f"hareket kalıbı >= {MIN_MOTION_PATTERNS}",
        "layout özellikleri animasyon/transition'da kullanılmıyor",
        "prefers-reduced-motion sorgusu var",
        f">= {MIN_EASINGS} farklı easing",
    )
    return (Check("index.html var", False, reason), *(Check(n, False, reason) for n in names))


def inspect(workdir: Path, values: Mapping[str, str]) -> Inspection:
    """Ajanın animasyonlu sayfasını bağımsız ölç."""
    if not (workdir / "index.html").is_file():
        return Inspection(checks=_missing_output_checks())
    sources = collect_sources(workdir)
    css = lint.analyse_css(sources.css)
    try:
        report = measure_runtime(workdir)
    except BrowserUnavailableError as error:
        return Inspection(invalid_reason=str(error))
    except PageInteractionError as error:
        runtime = _failed_runtime(f"sayfa ölçülemedi: {str(error)[:160]}")
        live = 0
    else:
        runtime = _runtime_checks(report)
        live = report.max_live_animations
    present = Check("index.html var", True, f"{len(sources.html)} bayt html")
    checks = (present, *runtime, *_source_checks(sources, css, live))
    return Inspection(checks=checks)


AREA = Area(name="animasyon", task=TASK, timeout_s=TIMEOUT_S, inspect=inspect)

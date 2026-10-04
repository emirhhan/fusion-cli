"""`evals/kabul/areas/animation.py` denetçisinin testleri.

Saf kısımlar (CSS lint) doğrudan; tarayıcı gerektirenler playwright yoksa atlanır.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from evals.kabul.areas import _motion_lint as lint
from evals.kabul.areas import animation
from evals.kabul.model import Inspection

GOOD_PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>Kahve</title>
<style>
  body { margin: 0; font-family: sans-serif; background: #2b1a10; color: #f5e6d3; }
  section { min-height: 100vh; padding: 4rem; display: flex; flex-direction: column;
            justify-content: center; }
  h1 { font-size: 7rem; margin: 0; animation: heroIn 1.2s cubic-bezier(.16,1,.3,1) both; }
  .badge { animation: pulse 2s ease-in-out infinite; width: 80px; height: 80px;
           background: #c97b3c; border-radius: 50%; }
  .card { background: #c97b3c; padding: 2rem; margin: 1rem 0; opacity: 0;
          transform: translateY(40px);
          transition: opacity .7s ease-out, transform .7s ease-out; }
  .card.visible { opacity: 1; transform: none; }
  .card:hover { transform: scale(1.04); background: #e09a5c; }
  a { transition: color .3s linear, background-color .3s ease-in; }
  @keyframes heroIn { from { opacity: 0; transform: translateY(60px); } to { opacity: 1; } }
  @keyframes pulse { 50% { transform: scale(1.15); } }
  @keyframes drift { to { transform: translateX(20px); } }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; } }
</style></head>
<body>
<section><h1>Kahve</h1><div class="badge"></div></section>
<section><div class="card">Çekirdek</div><div class="card">Kavurma</div>
<div class="card">Demleme</div><div class="card">Sofra</div></section>
<script>
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) entry.target.classList.add('visible');
    });
  }, { threshold: 0.2 });
  document.querySelectorAll('.card').forEach((card) => observer.observe(card));
</script>
</body></html>
"""

STATIC_PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>Kahve</title>
<style>
  body { margin: 0; background: #2b1a10; color: #f5e6d3; }
  section { min-height: 100vh; padding: 4rem; }
  h1 { font-size: 7rem; margin: 0; }
  .card { background: #c97b3c; padding: 2rem; margin: 1rem 0; }
</style></head>
<body><section><h1>Kahve</h1></section>
<section><div class="card">Çekirdek</div><div class="card">Kavurma</div></section>
</body></html>
"""


def _inspect(workdir: Path) -> Inspection:
    return animation.inspect(workdir, {})


def _by_name(inspection: Inspection) -> dict[str, bool]:
    return {check.name: check.passed for check in inspection.checks}


def _require_browser() -> None:
    pytest.importorskip("playwright.sync_api")


# --- Saf CSS lint -----------------------------------------------------------


def test_layout_property_detection_covers_margin_and_padding_variants():
    assert lint.is_layout_property("margin-left")
    assert lint.is_layout_property("padding")
    assert lint.is_layout_property("Width")
    assert not lint.is_layout_property("transform")
    assert not lint.is_layout_property("opacity")


def test_analyse_css_counts_keyframes_and_transition_items():
    css = """
    @keyframes a { from { opacity: 0 } to { opacity: 1 } }
    @keyframes b { 50% { transform: scale(1.1) } }
    .x { transition: opacity .3s ease, transform .3s cubic-bezier(.2, .8, .2, 1); }
    .y { transition: none; }
    """
    motion = lint.analyse_css(css)
    assert motion.keyframe_names == ("a", "b")
    assert motion.transition_count == 2
    assert motion.pattern_count == 4
    assert "ease" in motion.easings
    assert "cubic-bezier(.2,.8,.2,1)" in motion.easings


def test_analyse_css_flags_layout_properties_in_keyframes_and_transitions():
    css = """
    @keyframes grow { from { width: 0 } to { width: 200px; margin-left: 10px } }
    .box { transition: height .3s ease, opacity .3s; }
    .ok { transition: transform .3s; }
    """
    hits = lint.analyse_css(css).layout_hits
    assert "@keyframes grow:width" in hits
    assert "@keyframes grow:margin-left" in hits
    assert "transition:height" in hits
    assert not any("transform" in hit or "opacity" in hit for hit in hits)


def test_analyse_css_ignores_comments_and_clean_motion_has_no_hits():
    css = "/* transition: width 1s */ .a { transition: opacity .2s linear; }"
    motion = lint.analyse_css(css)
    assert motion.layout_hits == ()
    assert motion.transition_count == 1


def test_reduced_motion_query_is_detected_in_css_and_js():
    assert lint.has_reduced_motion_query("@media (prefers-reduced-motion: reduce) {}")
    assert lint.has_reduced_motion_query("matchMedia('(prefers-reduced-motion)')")
    assert not lint.has_reduced_motion_query("body { color: red }")


def test_js_easings_reads_easing_options():
    assert lint.js_easings(
        "el.animate(k, { easing: 'ease-out' }); gsap.to(a, {ease: 'power2.out'})"
    ) == (
        "ease-out",
        "power2.out",
    )


# --- Çıktı yok --------------------------------------------------------------


def test_missing_index_fails_every_check_without_invalid_reason(tmp_path):
    inspection = _inspect(tmp_path)
    assert inspection.invalid_reason == ""
    assert inspection.checks
    assert not any(check.passed for check in inspection.checks)
    assert not inspection.all_passed


def test_area_declares_name_and_timeout():
    assert animation.AREA.name == "animasyon"
    assert animation.AREA.timeout_s == 3600


# --- Tarayıcılı ölçüm -------------------------------------------------------


def test_good_animated_page_passes_all_checks(tmp_path):
    _require_browser()
    (tmp_path / "index.html").write_text(GOOD_PAGE, encoding="utf-8")
    inspection = _inspect(tmp_path)
    if inspection.invalid_reason:
        pytest.skip(inspection.invalid_reason)
    failed = [f"{c.name}: {c.detail}" for c in inspection.checks if not c.passed]
    assert failed == []
    assert inspection.all_passed


def test_static_page_fails_motion_related_checks(tmp_path):
    _require_browser()
    (tmp_path / "index.html").write_text(STATIC_PAGE, encoding="utf-8")
    inspection = _inspect(tmp_path)
    if inspection.invalid_reason:
        pytest.skip(inspection.invalid_reason)
    results = _by_name(inspection)
    assert results["index.html var"]
    assert results["konsol hatası 0"]
    assert not results["t=0/700/1600 ms kareleri arasında hareket var"]
    assert not results["kaydırınca yeni öğeler görünür hale gelir"]
    assert not results[f"hareket kalıbı >= {animation.MIN_MOTION_PATTERNS}"]
    assert not results["prefers-reduced-motion sorgusu var"]
    assert not results[f">= {animation.MIN_EASINGS} farklı easing"]


def test_console_error_page_fails_console_check(tmp_path):
    _require_browser()
    broken = GOOD_PAGE.replace("</body>", "<script>undefinedFunction();</script></body>")
    (tmp_path / "index.html").write_text(broken, encoding="utf-8")
    inspection = _inspect(tmp_path)
    if inspection.invalid_reason:
        pytest.skip(inspection.invalid_reason)
    assert not _by_name(inspection)["konsol hatası 0"]


def test_layout_animation_fails_layout_check(tmp_path):
    _require_browser()
    bad = GOOD_PAGE.replace(
        "@keyframes drift { to { transform: translateX(20px); } }",
        "@keyframes drift { to { width: 300px; } }",
    )
    (tmp_path / "index.html").write_text(bad, encoding="utf-8")
    inspection = _inspect(tmp_path)
    if inspection.invalid_reason:
        pytest.skip(inspection.invalid_reason)
    assert not _by_name(inspection)["layout özellikleri animasyon/transition'da kullanılmıyor"]


def test_easing_css_degiskeni_cozulerek_sayilir():
    from evals.kabul.areas._motion_lint import analyse_css

    css = (
        ":root{--ease-out:cubic-bezier(.16,1,.3,1);--ease-io:cubic-bezier(.65,0,.35,1)}"
        ".a{transition:opacity .3s var(--ease-out)}.b{animation:x 2s var(--ease-io) infinite}"
    )

    assert len(analyse_css(css).easings) == 2

"""`evals/kabul/areas/html_game.py` denetçisinin testleri.

Saf kısımlar (HUD ayrıştırma) doğrudan; tarayıcı gerektirenler playwright yoksa atlanır.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from evals.kabul.areas import _game_probe as probe
from evals.kabul.areas import html_game
from evals.kabul.model import Inspection

GAME_TEMPLATE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>Oyun</title>
<style>body{margin:0;background:#111} canvas{display:block;margin:20px auto}</style></head>
<body><canvas id="game" width="480" height="320"></canvas>
<script>
const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
const keys = {};
const SPEED = 300, SIZE = 24;
let player, enemy, score, lives, distance, last;
function reset() {
  player = {x: 200, y: 150}; enemy = {x: 40, y: 280, dir: 1};
  score = 0; lives = 3; distance = 0;
}
reset();
__KEY_HANDLERS__
function update(dt) {
  const before = {x: player.x, y: player.y};
  if (keys.ArrowRight) player.x += SPEED * dt;
  if (keys.ArrowLeft) player.x -= SPEED * dt;
  if (keys.ArrowUp) player.y -= SPEED * dt;
  if (keys.ArrowDown) player.y += SPEED * dt;
  player.x = Math.max(0, Math.min(canvas.width - SIZE, player.x));
  player.y = Math.max(0, Math.min(canvas.height - SIZE, player.y));
  distance += Math.hypot(player.x - before.x, player.y - before.y);
  score = Math.floor(distance / 100);
  enemy.x += enemy.dir * 20 * dt;
  if (enemy.x > 440 || enemy.x < 10) enemy.dir *= -1;
}
function draw() {
  ctx.fillStyle = '#1b2838'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#ffd166'; ctx.fillRect(player.x, player.y, SIZE, SIZE);
  ctx.fillStyle = '#ef476f'; ctx.fillRect(enemy.x, enemy.y, 16, 16);
  ctx.fillStyle = '#ffffff'; ctx.font = '16px sans-serif';
  ctx.fillText('Skor: ' + score, 10, 20);
  ctx.fillText('Can: ' + lives, 400, 20);
}
function frame(now) {
  const dt = Math.min(0.05, ((now - (last || now)) / 1000));
  last = now; update(dt); draw(); requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script></body></html>
"""

LIVE_HANDLERS = """
addEventListener('keydown', (event) => {
  keys[event.code] = true;
  if (event.code === 'KeyR') reset();
  if (event.code.startsWith('Arrow') || event.code === 'Space') event.preventDefault();
});
addEventListener('keyup', (event) => { keys[event.code] = false; });
"""

GOOD_GAME = GAME_TEMPLATE.replace("__KEY_HANDLERS__", LIVE_HANDLERS)
DEAD_KEYS_GAME = GAME_TEMPLATE.replace("__KEY_HANDLERS__", "")
BLANK_GAME = (
    "<!doctype html><title>Oyun</title><canvas id='game' width='480' height='320'></canvas>"
)


def _inspect(workdir: Path) -> Inspection:
    return html_game.inspect(workdir, {})


def _by_name(inspection: Inspection) -> dict[str, bool]:
    return {check.name: check.passed for check in inspection.checks}


def _run(tmp_path: Path, page: str) -> Inspection:
    pytest.importorskip("playwright.sync_api")
    (tmp_path / "index.html").write_text(page, encoding="utf-8")
    inspection = _inspect(tmp_path)
    if inspection.invalid_reason:
        pytest.skip(inspection.invalid_reason)
    return inspection


# --- Saf kısımlar -----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["Skor: 12", "SCORE 340", "Can: 3", "Lives: 2", "HP=80", "♥♥♥", "120 puan", "Puan:0"],
)
def test_hud_pattern_matches_score_and_lives_texts(text):
    assert probe.HUD_PATTERN.search(text)


@pytest.mark.parametrize("text", ["Oyunu başlat", "You can play with arrows", "Game Over"])
def test_hud_pattern_ignores_plain_text(text):
    assert not probe.HUD_PATTERN.search(text)


def test_hud_reading_merges_and_sorts_dom_and_canvas_lines():
    reading = probe.HudReading(dom=("Skor: 3",), canvas=("Can: 2", "Skor: 3"))
    assert reading.lines == ("Can: 2", "Skor: 3")
    assert reading.found
    assert not probe.HudReading().found


def test_area_declares_name_and_timeout():
    assert html_game.AREA.name == "html_oyun"
    assert html_game.AREA.timeout_s == 3600


# --- Çıktı yok --------------------------------------------------------------


def test_missing_index_fails_every_check_without_invalid_reason(tmp_path):
    inspection = _inspect(tmp_path)
    assert inspection.invalid_reason == ""
    assert [check.name for check in inspection.checks] == list(html_game.CHECK_NAMES)
    assert not any(check.passed for check in inspection.checks)


# --- Tarayıcılı ölçüm -------------------------------------------------------


@pytest.fixture(scope="module")
def good_inspection(tmp_path_factory) -> Inspection:
    return _run(tmp_path_factory.mktemp("game_good"), GOOD_GAME)


@pytest.fixture(scope="module")
def dead_keys_inspection(tmp_path_factory) -> Inspection:
    return _run(tmp_path_factory.mktemp("game_dead_keys"), DEAD_KEYS_GAME)


def test_good_game_passes_all_checks(good_inspection):
    inspection = good_inspection
    failed = [f"{c.name}: {c.detail}" for c in inspection.checks if not c.passed]
    assert failed == []
    assert inspection.all_passed


def test_game_ignoring_keys_fails_key_and_restart_checks(dead_keys_inspection):
    results = _by_name(dead_keys_inspection)
    assert results["index.html var"]
    assert results["requestAnimationFrame döngüsü çalışıyor"]
    assert results["skor/can HUD'ı var"]
    assert not results["ok tuşları + boşluk oyunu değiştiriyor"]
    assert not results["yeniden başlat durumu sıfırlıyor"]


def test_blank_canvas_fails_area_check(tmp_path):
    results = _by_name(_run(tmp_path, BLANK_GAME))
    assert not results["oyun alanı var ve boş değil"]


def test_page_without_canvas_or_game_area_fails_area_and_hud(tmp_path):
    results = _by_name(_run(tmp_path, "<!doctype html><title>x</title><p>Merhaba</p>"))
    assert not results["oyun alanı var ve boş değil"]
    assert not results["requestAnimationFrame döngüsü çalışıyor"]
    assert not results["skor/can HUD'ı var"]


def test_console_error_fails_console_check(tmp_path):
    broken = GOOD_GAME.replace("</body>", "<script>missingFunction();</script></body>")
    assert not _by_name(_run(tmp_path, broken))["konsol hatası 0"]


def test_dom_hud_without_canvas_text_is_detected(tmp_path):
    page = GOOD_GAME.replace("ctx.fillText('Skor: ' + score, 10, 20);", "").replace(
        "ctx.fillText('Can: ' + lives, 400, 20);", ""
    )
    page = page.replace("<canvas", "<div id='hud'>Skor: 0 Can: 3</div><canvas", 1)
    assert _by_name(_run(tmp_path, page))["skor/can HUD'ı var"]


GAME_OVER_ONLY_HANDLERS = """
let over = false, hurt = 0;
addEventListener('keydown', (event) => {
  keys[event.code] = true;
  if (event.code === 'KeyR' && over) { reset(); over = false; hurt = 0; }
  if (event.code.startsWith('Arrow') || event.code === 'Space') event.preventDefault();
});
addEventListener('keyup', (event) => { keys[event.code] = false; });
setInterval(() => { if (!over && lives > 0) { lives -= 1; over = lives === 0; } }, 1000);
window.__GAME_STATE__ = () => ({ durum: over ? 'bitti' : 'oynuyor', skor: score, can: lives });
"""


def test_restart_only_on_game_over_with_state_hook_passes(tmp_path):
    """HUD yalnız sayı, R yalnız oyun bitince çalışır: geçerli tasarım, geçmeli."""
    page = (
        GAME_TEMPLATE.replace("__KEY_HANDLERS__", GAME_OVER_ONLY_HANDLERS)
        .replace("ctx.fillText('Skor: ' + score, 10, 20);", "ctx.fillText(String(score), 10, 20);")
        .replace("ctx.fillText('Can: ' + lives, 400, 20);", "")
    )
    results = _by_name(_run(tmp_path, page))
    assert results["skor/can HUD'ı var"]
    assert results["yeniden başlat durumu sıfırlıyor"]


def test_hud_reading_counts_state_hook_lines():
    reading = probe.HudReading(state=("skor: 0",))
    assert reading.found
    assert reading.lines == ("skor: 0",)

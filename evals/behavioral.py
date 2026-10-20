"""Davranışsal post-run acceptance kontrolleri.

Bu modül AGENT'ın parçası değildir. Eval görevi bittikten sonra scratch workspace'e
karşı ayrı çalışır; böylece model kendi evaluator'ını okuyup değiştiremez.

Kullanım:
    python -m evals.behavioral arena
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol, cast

Snapshot = Mapping[str, object]
Predicate = Callable[[Snapshot], bool]


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    """Bir davranışsal senaryonun tek tek ölçülmüş sonuçları."""

    checks: Mapping[str, bool]
    details: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(self.checks.values())


class ArenaDriver(Protocol):
    """Arena acceptance mantığının ihtiyaç duyduğu dar tarayıcı yüzeyi."""

    def restart(self) -> None: ...

    def snapshot(self) -> Snapshot: ...

    def spawn_enemy(self, options: Mapping[str, object]) -> object: ...

    def spawn_xp(self, options: Mapping[str, object]) -> None: ...

    def wait_until(
        self,
        predicate: Predicate,
        *,
        timeout_s: float = 3.0,
    ) -> Snapshot | None: ...


def evaluate_arena(driver: ArenaDriver) -> AcceptanceResult:
    """Arena survival oyununun minimum gerçek oynanış döngüsünü ölç."""

    checks: dict[str, bool] = {}
    details: list[str] = []

    try:
        checks["projectile_damages_enemy"] = _projectile_damages_enemy(driver)
    except (KeyError, TypeError, ValueError) as exc:
        checks["projectile_damages_enemy"] = False
        details.append(f"projectile_damages_enemy: {exc}")

    try:
        checks["enemy_can_die_and_drop_xp"] = _enemy_can_die_and_drop_xp(driver)
    except (KeyError, TypeError, ValueError) as exc:
        checks["enemy_can_die_and_drop_xp"] = False
        details.append(f"enemy_can_die_and_drop_xp: {exc}")

    try:
        checks["player_takes_damage"] = _player_takes_damage(driver)
    except (KeyError, TypeError, ValueError) as exc:
        checks["player_takes_damage"] = False
        details.append(f"player_takes_damage: {exc}")

    try:
        checks["xp_can_level_up"] = _xp_can_level_up(driver)
    except (KeyError, TypeError, ValueError) as exc:
        checks["xp_can_level_up"] = False
        details.append(f"xp_can_level_up: {exc}")

    return AcceptanceResult(checks=checks, details=tuple(details))


def _projectile_damages_enemy(driver: ArenaDriver) -> bool:
    driver.restart()
    before = driver.snapshot()
    player = _player(before)

    enemy_id = driver.spawn_enemy(
        {
            "x": _number(player, "x") + 70,
            "y": _number(player, "y"),
            "hp": 100,
            "speed": 0,
        }
    )

    spawned = driver.wait_until(
        lambda snapshot: _enemy(snapshot, enemy_id) is not None,
        timeout_s=1.0,
    )
    if spawned is None:
        return False

    enemy = _enemy(spawned, enemy_id)
    if enemy is None:
        return False
    initial_hp = _number(enemy, "hp")

    damaged = driver.wait_until(
        lambda snapshot: _enemy_hp_below(snapshot, enemy_id, initial_hp),
        timeout_s=3.0,
    )
    return damaged is not None


def _enemy_can_die_and_drop_xp(driver: ArenaDriver) -> bool:
    driver.restart()
    before = driver.snapshot()
    player = _player(before)
    xp_before = _number(player, "xp")
    gems_before = len(_objects(before, "xpGems"))

    enemy_id = driver.spawn_enemy(
        {
            "x": _number(player, "x") + 55,
            "y": _number(player, "y"),
            "hp": 1,
            "speed": 0,
        }
    )

    result = driver.wait_until(
        lambda snapshot: (
            _enemy(snapshot, enemy_id) is None
            and (
                len(_objects(snapshot, "xpGems")) > gems_before
                or _number(_player(snapshot), "xp") > xp_before
            )
        ),
        timeout_s=3.0,
    )
    return result is not None


def _player_takes_damage(driver: ArenaDriver) -> bool:
    driver.restart()
    before = driver.snapshot()
    player = _player(before)
    hp_before = _number(player, "hp")

    driver.spawn_enemy(
        {
            "x": _number(player, "x"),
            "y": _number(player, "y"),
            "hp": 1000,
            "speed": 0,
        }
    )

    result = driver.wait_until(
        lambda snapshot: _number(_player(snapshot), "hp") < hp_before,
        timeout_s=2.0,
    )
    return result is not None


def _xp_can_level_up(driver: ArenaDriver) -> bool:
    driver.restart()
    before = driver.snapshot()
    player = _player(before)
    level_before = _number(player, "level")

    driver.spawn_xp(
        {
            "x": _number(player, "x"),
            "y": _number(player, "y"),
            "value": 10_000,
        }
    )

    result = driver.wait_until(
        lambda snapshot: _number(_player(snapshot), "level") > level_before,
        timeout_s=2.0,
    )
    return result is not None


def _player(snapshot: Snapshot) -> Mapping[str, object]:
    value = snapshot.get("player")
    if not isinstance(value, Mapping):
        raise TypeError("snapshot.player nesne olmalı")
    return cast(Mapping[str, object], value)


def _objects(snapshot: Snapshot, key: str) -> list[Mapping[str, object]]:
    value = snapshot.get(key)
    if not isinstance(value, list):
        raise TypeError(f"snapshot.{key} liste olmalı")

    result: list[Mapping[str, object]] = []
    for item in value:
        if isinstance(item, Mapping):
            result.append(cast(Mapping[str, object], item))
    return result


def _enemy(snapshot: Snapshot, enemy_id: object) -> Mapping[str, object] | None:
    for enemy in _objects(snapshot, "enemies"):
        if enemy.get("id") == enemy_id:
            return enemy
    return None


def _enemy_hp_below(
    snapshot: Snapshot,
    enemy_id: object,
    initial_hp: float,
) -> bool:
    enemy = _enemy(snapshot, enemy_id)
    if enemy is None:
        # Normal damage zinciri düşmanı tamamen öldürmüşse bu da hasarın kanıtıdır.
        return True
    return _number(enemy, "hp") < initial_hp


def _number(mapping: Mapping[str, object], key: str) -> float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} sayısal olmalı")
    return float(value)


class _PlaywrightArenaDriver:
    """Gerçek Playwright sayfasını ArenaDriver sözleşmesine uyarlar."""

    def __init__(self, page: object) -> None:
        self._page = page

    def ensure_contract(self) -> None:
        page = self._page
        page.wait_for_function(  # type: ignore[attr-defined]
            """() => {
                const d = window.__FUSION_GAME_DEBUG__;
                return d
                    && typeof d.snapshot === 'function'
                    && typeof d.spawnEnemy === 'function'
                    && typeof d.spawnXp === 'function'
                    && typeof d.restart === 'function';
            }""",
            timeout=5_000,
        )

    def restart(self) -> None:
        self._page.evaluate(  # type: ignore[attr-defined]
            "() => window.__FUSION_GAME_DEBUG__.restart()"
        )
        time.sleep(0.05)

    def snapshot(self) -> Snapshot:
        value = self._page.evaluate(  # type: ignore[attr-defined]
            "() => window.__FUSION_GAME_DEBUG__.snapshot()"
        )
        if not isinstance(value, Mapping):
            raise TypeError("debug snapshot nesne döndürmedi")
        return cast(Snapshot, value)

    def spawn_enemy(self, options: Mapping[str, object]) -> object:
        return self._page.evaluate(  # type: ignore[attr-defined]
            "(opts) => window.__FUSION_GAME_DEBUG__.spawnEnemy(opts)",
            dict(options),
        )

    def spawn_xp(self, options: Mapping[str, object]) -> None:
        self._page.evaluate(  # type: ignore[attr-defined]
            "(opts) => window.__FUSION_GAME_DEBUG__.spawnXp(opts)",
            dict(options),
        )

    def wait_until(
        self,
        predicate: Predicate,
        *,
        timeout_s: float = 3.0,
    ) -> Snapshot | None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            snapshot = self.snapshot()
            if predicate(snapshot):
                return snapshot
            time.sleep(0.05)
        return None


@contextmanager
def _serve(root: Path) -> Iterator[str]:
    """Scratch workspace'i yalnız localhost üzerinde geçici olarak sun."""

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        port = server.server_address[1]
        yield f"http://127.0.0.1:{port}/index.html"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def run_arena_browser(root: Path) -> AcceptanceResult:
    """Gerçek Chromium üzerinde arena acceptance kontrollerini çalıştır."""

    if not (root / "index.html").is_file():
        return AcceptanceResult(
            checks={"index_html_exists": False},
            details=("index.html bulunamadı",),
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return AcceptanceResult(
            checks={"playwright_available": False},
            details=(
                "Playwright kurulu değil; önce `pip install -e .[web]`, "
                "sonra `playwright install chromium` çalıştır.",
            ),
        )

    console_errors: list[str] = []

    with _serve(root) as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.on(
                "console",
                lambda message: (
                    console_errors.append(message.text) if message.type == "error" else None
                ),
            )
            page.on("pageerror", lambda error: console_errors.append(str(error)))
            page.goto(url, wait_until="load", timeout=15_000)

            driver = _PlaywrightArenaDriver(page)
            try:
                driver.ensure_contract()
            except Exception as exc:
                return AcceptanceResult(
                    checks={"debug_contract": False},
                    details=(f"window.__FUSION_GAME_DEBUG__ sözleşmesi yok: {exc}",),
                )

            result = evaluate_arena(driver)
            checks = dict(result.checks)
            checks["console_clean"] = not console_errors
            details = list(result.details)
            details.extend(f"console: {item}" for item in console_errors)

            return AcceptanceResult(
                checks=checks,
                details=tuple(details),
            )
        finally:
            browser.close()


def _print_result(result: AcceptanceResult) -> None:
    for name, ok in result.checks.items():
        marker = "PASS" if ok else "FAIL"
        print(f"{marker:4} {name}")
    for detail in result.details:
        print(f"     {detail}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args != ["arena"]:
        print("kullanım: python -m evals.behavioral arena")
        return 2

    result = run_arena_browser(Path.cwd())
    _print_result(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

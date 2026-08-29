from __future__ import annotations

import os
from pathlib import Path

from evals.behavioral import evaluate_arena
from evals.executor import _verification_env
from evals.loader import load_tasks


class _FakeArena:
    def __init__(self, *, progresses: bool = True) -> None:
        self.progresses = progresses
        self._next_id = 0
        self.restart()

    def restart(self) -> None:
        self.player = {
            "x": 100.0,
            "y": 100.0,
            "hp": 10.0,
            "maxHp": 10.0,
            "level": 1,
            "xp": 0.0,
        }
        self.enemies: list[dict[str, object]] = []
        self.gems: list[dict[str, object]] = []

    def snapshot(self):
        return {
            "player": dict(self.player),
            "enemies": [dict(item) for item in self.enemies],
            "xpGems": [dict(item) for item in self.gems],
            "gameOver": False,
        }

    def spawn_enemy(self, options):
        self._next_id += 1
        enemy = {
            "id": self._next_id,
            "x": float(options["x"]),
            "y": float(options["y"]),
            "hp": float(options["hp"]),
            "maxHp": float(options["hp"]),
            "speed": float(options["speed"]),
        }
        self.enemies.append(enemy)
        return self._next_id

    def spawn_xp(self, options):
        self.gems.append(
            {
                "x": float(options["x"]),
                "y": float(options["y"]),
                "value": float(options["value"]),
            }
        )

    def wait_until(self, predicate, *, timeout_s=3.0):
        for _ in range(6):
            snapshot = self.snapshot()
            if predicate(snapshot):
                return snapshot
            self._tick()
        return None

    def _tick(self):
        if not self.progresses:
            return

        kalan = []
        for enemy in self.enemies:
            if (
                float(enemy["hp"]) >= 1000
                and float(enemy["x"]) == float(self.player["x"])
                and float(enemy["y"]) == float(self.player["y"])
            ):
                self.player["hp"] = float(self.player["hp"]) - 1
                kalan.append(enemy)
                continue

            enemy["hp"] = float(enemy["hp"]) - 1
            if float(enemy["hp"]) <= 0:
                self.gems.append(
                    {
                        "x": enemy["x"],
                        "y": enemy["y"],
                        "value": 1.0,
                    }
                )
            else:
                kalan.append(enemy)

        self.enemies = kalan

        gems = []
        for gem in self.gems:
            if float(gem["x"]) == float(self.player["x"]) and float(gem["y"]) == float(
                self.player["y"]
            ):
                self.player["xp"] = float(self.player["xp"]) + float(gem["value"])
                self.player["level"] = int(self.player["level"]) + 1
            else:
                gems.append(gem)
        self.gems = gems


def test_arena_core_loop_dogru_uygulamada_gecer():
    result = evaluate_arena(_FakeArena())

    assert result.ok
    assert result.checks == {
        "projectile_damages_enemy": True,
        "enemy_can_die_and_drop_xp": True,
        "player_takes_damage": True,
        "xp_can_level_up": True,
    }


def test_arena_sadece_state_uretmekle_gecmez():
    result = evaluate_arena(_FakeArena(progresses=False))

    assert not result.ok
    assert result.checks["projectile_damages_enemy"] is False
    assert result.checks["enemy_can_die_and_drop_xp"] is False
    assert result.checks["player_takes_damage"] is False
    assert result.checks["xp_can_level_up"] is False


def test_arena_suite_mevcut_eval_loaderiyla_yuklenir():
    suite = Path(__file__).resolve().parents[1] / "evals" / "suite" / "arena.yaml"

    tasks = load_tasks(suite)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.id == "arena-survival-core-loop"
    assert task.criterion.command == "python -m evals.behavioral arena"


def test_verification_env_repo_evals_paketini_bulabilir():
    env = _verification_env()
    repo = str(Path(__file__).resolve().parents[1])

    assert repo in env["PYTHONPATH"].split(os.pathsep)


def test_reference_arena_gercek_chromiumda_gecer():
    from evals.behavioral import run_arena_browser

    root = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "arena_reference"

    result = run_arena_browser(root)

    assert result.ok, (result.checks, result.details)


def test_bozuk_arena_console_temiz_olsa_da_davranistan_kalir():
    from evals.behavioral import run_arena_browser

    root = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "arena_broken"

    result = run_arena_browser(root)

    assert result.ok is False
    assert result.checks["console_clean"] is True
    assert result.checks["projectile_damages_enemy"] is False
    assert result.checks["enemy_can_die_and_drop_xp"] is False
    assert result.checks["player_takes_damage"] is False
    assert result.checks["xp_can_level_up"] is False

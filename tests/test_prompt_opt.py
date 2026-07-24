"""Faz 6 — offline prompt optimizasyonu: seçim, sürümleme ve optimize döngüsü.

Regresyon korumalı seçim, sürüm deposu ve optimize akışı; optimizasyon çağrıları
(varyant üretimi + değerlendirme) mock'lanarak ağsız test edilir.
"""

from __future__ import annotations

import pytest
from evals.metrics import RunReport, TaskResult
from prompt_opt.optimizer import optimize
from prompt_opt.selection import Candidate, select_winner
from prompt_opt.variants import PromptVariant
from prompt_opt.versioning import PromptStore


def _report(success: dict[str, bool]) -> RunReport:
    return RunReport(
        results=tuple(
            TaskResult(
                task_id=task_id,
                success=ok,
                first_attempt_success=ok,
                retries=0,
                model_calls=1,
                duration_seconds=1.0,
            )
            for task_id, ok in success.items()
        )
    )


def _candidate(text: str, success: dict[str, bool], version: int = 0) -> Candidate:
    return Candidate(PromptVariant("planner", text, version), _report(success))


# --------------------------------------------------------------------------- #
# Seçim (regresyon korumalı) — saf
# --------------------------------------------------------------------------- #


def test_iyilestiren_aday_secilir():
    baseline = _candidate("v0", {"a": True, "b": False, "c": False})
    better = _candidate("v1", {"a": True, "b": True, "c": True})
    selection = select_winner(baseline, (better,), min_improvement=0.02)
    assert selection.improved is True
    assert selection.winner.text == "v1"


def test_regresyon_yapan_aday_elenir():
    baseline = _candidate("v0", {"a": True, "b": True, "c": False})
    # 'a' bozuldu (regresyon), 'c' düzeldi → toplam aynı ama regresyon var: elenmeli.
    regressor = _candidate("v1", {"a": False, "b": True, "c": True})
    selection = select_winner(baseline, (regressor,), min_improvement=0.0)
    assert selection.improved is False
    assert selection.winner.text == "v0"


def test_yetersiz_iyilesme_temeli_korur():
    baseline = _candidate("v0", {"a": True, "b": False})
    marginal = _candidate("v1", {"a": True, "b": False})  # aynı skor
    selection = select_winner(baseline, (marginal,), min_improvement=0.02)
    assert selection.improved is False


def test_en_cok_iyilestiren_aday_kazanir():
    baseline = _candidate("v0", {"a": False, "b": False, "c": False, "d": False})
    az = _candidate("az", {"a": True, "b": False, "c": False, "d": False})
    cok = _candidate("cok", {"a": True, "b": True, "c": True, "d": False})
    selection = select_winner(baseline, (az, cok), min_improvement=0.02)
    assert selection.winner.text == "cok"


# --------------------------------------------------------------------------- #
# Sürüm deposu
# --------------------------------------------------------------------------- #


def test_yayim_surumu_artirir(tmp_path):
    store = PromptStore(tmp_path)
    v1 = store.publish("planner", "ilk")
    v2 = store.publish("planner", "ikinci")
    assert v1.version == 1
    assert v2.version == 2
    assert store.current("planner").text == "ikinci"


def test_gecmis_korunur(tmp_path):
    store = PromptStore(tmp_path)
    store.publish("planner", "a")
    store.publish("planner", "b")
    assert [v.text for v in store.history("planner")] == ["a", "b"]


def test_hic_yayim_yoksa_current_none(tmp_path):
    assert PromptStore(tmp_path).current("planner") is None


def test_rollback_eski_surumu_yeniden_yayimlar(tmp_path):
    store = PromptStore(tmp_path)
    store.publish("planner", "a")
    store.publish("planner", "b")
    rolled = store.rollback("planner", 1)
    assert rolled.text == "a"
    assert rolled.version == 3
    assert store.current("planner").text == "a"


def test_rollback_olmayan_surum_hata(tmp_path):
    store = PromptStore(tmp_path)
    store.publish("planner", "a")
    with pytest.raises(ValueError):
        store.rollback("planner", 99)


# --------------------------------------------------------------------------- #
# Optimize döngüsü (mock üretici + değerlendirici)
# --------------------------------------------------------------------------- #


class _FakeGenerator:
    def __init__(self, variants: tuple[str, ...]) -> None:
        self._variants = variants

    async def generate(self, base_text: str, count: int) -> tuple[str, ...]:
        return self._variants[:count]


class _FakeEvaluator:
    """Metin → başarı haritası eşlemesiyle deterministik değerlendirici."""

    def __init__(self, scores: dict[str, dict[str, bool]]) -> None:
        self._scores = scores

    async def evaluate(self, prompt_text: str) -> RunReport:
        return _report(self._scores[prompt_text])


async def test_optimize_iyilesme_varsa_yayimlar(tmp_path):
    store = PromptStore(tmp_path)
    generator = _FakeGenerator(("iyi",))
    evaluator = _FakeEvaluator(
        {
            "temel": {"a": True, "b": False},
            "iyi": {"a": True, "b": True},
        }
    )
    selection = await optimize(
        "planner", "temel", generator=generator, evaluator=evaluator, store=store
    )
    assert selection.improved is True
    assert selection.winner.text == "iyi"
    assert store.current("planner").text == "iyi"


async def test_optimize_iyilesme_yoksa_yayimlamaz(tmp_path):
    store = PromptStore(tmp_path)
    generator = _FakeGenerator(("kotu",))
    evaluator = _FakeEvaluator(
        {
            "temel": {"a": True, "b": True},
            "kotu": {"a": True, "b": False},  # regresyon
        }
    )
    selection = await optimize(
        "planner", "temel", generator=generator, evaluator=evaluator, store=store
    )
    assert selection.improved is False
    assert store.current("planner") is None  # hiçbir şey yayımlanmadı

"""Canlı sürücünün uzun görev sayaçları: model, öğretmen, hata, yedeğe geçiş."""

from __future__ import annotations

from evals.live_drive import _say


def test_olaylar_rapor_sayaclarina_islenir() -> None:
    sayac = dict.fromkeys(
        ("model_cagrisi", "ogretmen_cagrisi", "arac_hatasi", "yedege_gecis",
         "sozlesme_onarimi", "hafizadan_plan"),
        0,
    )  # fmt: skip
    for veri in (
        {"olay": "ModelCallStarted"},
        {"olay": "ModelCallStarted", "background": True},
        {"olay": "ToolExecuted", "name": "ask_teacher", "outcome": "ok"},
        {"olay": "ToolExecuted", "name": "run_shell", "outcome": "failed"},
        {"olay": "ModelFallbackActivated"},
        {"olay": "ToolCallRepaired"},
        {"olay": "TeacherMemoryUsed"},
    ):
        _say(sayac, veri)

    assert sayac == {
        "model_cagrisi": 1, "ogretmen_cagrisi": 1, "arac_hatasi": 1,
        "yedege_gecis": 1, "sozlesme_onarimi": 1, "hafizadan_plan": 1,
    }  # fmt: skip

"""Zayıf model girdisi toleransı (T2-31, T1-45) ve emulation (T1-53/54)."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import TodoStatus, ToolContext
from fusion_cli.tools import desktop_background
from fusion_cli.tools.args import coerce_int
from fusion_cli.tools.planning import parse_todos, todo_write


@pytest.mark.parametrize(
    ("ham", "beklenen"),
    [
        ("done", TodoStatus.COMPLETED),
        ("Completed", TodoStatus.COMPLETED),
        ("finished", TodoStatus.COMPLETED),
        ("x", TodoStatus.COMPLETED),
        ("in-progress", TodoStatus.IN_PROGRESS),
        ("doing", TodoStatus.IN_PROGRESS),
        ("in progress", TodoStatus.IN_PROGRESS),
        ("todo", TodoStatus.PENDING),
        ("waiting", TodoStatus.PENDING),
    ],
)
def test_todo_durum_es_anlamlilari(ham, beklenen):
    """T2-31: `done`/`in-progress` gibi değerler sessizce `pending` yapılıp iş yarım sayılıyordu."""
    (madde,) = parse_todos([{"content": "a", "status": ham}])

    assert madde.status is beklenen


def test_todo_alan_adi_takma_adlari():
    (madde,) = parse_todos([{"task": "yaz", "status": "done"}, {"title": "oku"}][:1])

    assert madde.content == "yaz"
    assert parse_todos([{"title": "oku"}])[0].content == "oku"
    assert parse_todos([{"step": "test"}])[0].content == "test"


def test_todo_bilinmeyen_durum_sonucta_uyarilir():
    sonuc = todo_write({"todos": [{"content": "a", "status": "bambaska"}]}, ToolContext(root="."))

    assert sonuc.ok
    assert "bambaska" in sonuc.output and "beklemede" in sonuc.output


@pytest.mark.parametrize(
    ("ham", "beklenen"),
    [
        (5, 5),
        ("5", 5),
        (" 12 ", 12),
        (7.0, 7),
        (True, None),
        (7.5, None),
        ("x", None),
        (None, None),
    ],
)
def test_coerce_int(ham, beklenen):
    assert coerce_int(ham) == beklenen


def test_masaustu_arka_plan_hedefi_metin_ve_float_kabul_eder():
    """T1-45: `"1234"` / `1234.0` zayıf modellerde sık; sıkı `type() is int` tur kaybettiriyordu."""
    assert desktop_background._target({"window_id": "1234", "pid": 99.0}) == {
        "kind": "window",
        "id": 1234,
        "pid": 99,
    }
    assert desktop_background._target({"window_id": True, "pid": 1}) is None
    assert desktop_background._target({"window_id": 0, "pid": 1}) is None

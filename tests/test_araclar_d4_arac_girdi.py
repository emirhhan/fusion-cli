"""Zayıf model girdisi toleransı (T2-31, T1-45) ve emulation (T1-53/54)."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import TodoStatus, ToolContext
from fusion_cli.tools import desktop_background
from fusion_cli.tools.args import ArgumentError, coerce_int
from fusion_cli.tools.planning import parse_todos, todo_write


@pytest.mark.parametrize("ham", ["done", "Completed", "in-progress", "doing", "todo", None])
def test_todo_claude_disi_durum_reddedilir(ham):
    """#355: Claude'da durumlar yalnız pending/in_progress/completed; eş anlamlı yok."""
    with pytest.raises(ArgumentError, match="pending, in_progress, completed"):
        parse_todos([{"content": "a", "status": ham}])


def test_todo_claude_durumlari_kabul_edilir():
    maddeler = parse_todos(
        [
            {"content": "a", "status": "pending"},
            {"content": "b", "status": "in_progress"},
            {"content": "c", "status": "completed"},
        ]
    )
    assert [m.status for m in maddeler] == list(TodoStatus)


@pytest.mark.parametrize("alan", ["task", "title", "text", "step", "description"])
def test_todo_content_disindaki_alan_adi_reddedilir(alan):
    with pytest.raises(ArgumentError, match="'content' boş olamaz"):
        parse_todos([{alan: "yaz", "status": "pending"}])


def test_todo_bilinmeyen_durum_arac_hatasi_olur():
    with pytest.raises(ArgumentError, match="bambaska"):
        todo_write({"todos": [{"content": "a", "status": "bambaska"}]}, ToolContext(root="."))


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


# --- T1-53: emulation şema doğrulayıcı / tür dönüşümü ------------------------

from fusion_cli.tools.emulation import coerce_arguments, validate_arguments  # noqa: E402


def _sema(**properties):
    return {"parameters": {"type": "object", "properties": properties}}


def test_metin_sayi_ve_bool_dar_biçimde_cevrilir():
    """`"5"->5`, `"true"->True`: en sık zayıf-model hataları; yalnız şema tipi söylüyorsa."""
    sema = _sema(n={"type": "integer"}, b={"type": "boolean"}, s={"type": "string"})

    sonuc = coerce_arguments(sema, {"n": "5", "b": "true", "s": "5"})

    assert sonuc == {"n": 5, "b": True, "s": "5"}


def test_cevrilemeyen_metin_oldugu_gibi_kalir():
    sema = _sema(n={"type": "integer"}, b={"type": "boolean"})

    assert coerce_arguments(sema, {"n": "çok", "b": "belki"}) == {"n": "çok", "b": "belki"}


def test_tam_sayiya_json_float_kabul_edilir():
    assert validate_arguments(_sema(n={"type": "integer"}), {"n": 5.0}) == ()
    assert validate_arguments(_sema(n={"type": "integer"}), {"n": 5.5}) != ()


def test_type_listesi_ve_null():
    sema = _sema(a={"type": ["string", "null"]})

    assert validate_arguments(sema, {"a": None}) == ()
    assert validate_arguments(sema, {"a": "x"}) == ()
    assert validate_arguments(sema, {"a": 3}) != ()


def test_any_of_dallardan_biri_yeterli():
    sema = _sema(a={"anyOf": [{"type": "string"}, {"type": "integer"}]})

    assert validate_arguments(sema, {"a": 1}) == ()
    assert validate_arguments(sema, {"a": "x"}) == ()
    assert validate_arguments(sema, {"a": [1]}) != ()


def test_minimum_ve_min_items():
    sema = _sema(n={"type": "integer", "minimum": 1}, l={"type": "array", "minItems": 1})

    assert validate_arguments(sema, {"n": 0, "l": []}) != ()
    assert len(validate_arguments(sema, {"n": 0, "l": []})) == 2
    assert validate_arguments(sema, {"n": 1, "l": [1]}) == ()


# --- T1-54: emulation_eval ---------------------------------------------------

from fusion_cli.tools.emulation_eval import EvalCase, score_emulation  # noqa: E402

_OKU_SEMA = {
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
}


def _cagri(argumanlar: str) -> str:
    return f'<tool_call>{{"name":"read_file","arguments":{argumanlar}}}</tool_call>'


def test_ayristirilamayan_cagri_sema_ve_arguman_metriklerini_dusurur():
    """Hiç çağrı üretemeyen model şema/argüman metrikinde 1.0 alıyordu."""
    durumlar = [
        EvalCase("üzgünüm", "read_file", expected_arguments={"path": "a"}, schema=_OKU_SEMA)
        for _ in range(3)
    ]

    puan = score_emulation(durumlar)

    assert puan.schema_validity == 0.0 and puan.argument_preservation == 0.0
    assert puan.schema_validity_measured == 3
    assert not puan.passes()


def test_bozuk_arguman_json_i_istisna_atmaz():
    durum = EvalCase(
        _cagri('{"path": "a"'), "read_file", expected_arguments={"path": "a"}, schema=_OKU_SEMA
    )

    puan = score_emulation([durum] * 3)  # bozuk JSON: çağrı ayrıştırılamaz ya da arg bozuk

    assert not puan.passes()


def test_olcum_yoksa_ya_da_cok_azsa_gecmez():
    """0 ölçümde 1.0 "geçti" sayılmamalı; 2 senaryoda %100 da anlamsız (`min_cases`)."""
    assert not score_emulation([]).passes()
    iki = [EvalCase(_cagri('{"path": "a"}'), "read_file", schema=_OKU_SEMA)] * 2
    assert not score_emulation(iki).passes()
    uc = [EvalCase(_cagri('{"path": "a"}'), "read_file", schema=_OKU_SEMA)] * 3
    assert score_emulation(uc).passes()

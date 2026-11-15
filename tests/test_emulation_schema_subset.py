"""Taklit araçların desteklediği JSON Şeması alt kümesinin sınırları."""

from __future__ import annotations

import pytest

from fusion_cli.tools.emulation import validate_arguments


def _field_schema(schema):
    return {"parameters": {"type": "object", "properties": {"value": schema}}}


@pytest.mark.parametrize(("value", "is_valid"), [(1, False), (1.5, True), ("1", False)])
def test_one_of_tam_bir_dal_eslesmesi_ister(value, is_valid):
    schema = _field_schema({"oneOf": [{"type": "number"}, {"type": "integer"}]})

    assert (validate_arguments(schema, {"value": value}) == ()) is is_valid


def test_any_of_birden_fazla_eslesen_dali_kabul_eder():
    schema = _field_schema({"anyOf": [{"type": "number"}, {"type": "integer"}]})

    assert validate_arguments(schema, {"value": 1}) == ()


@pytest.mark.parametrize(("value", "is_valid"), [("allowed", True), (None, True), ("other", False)])
def test_birlesik_tur_enum_kisitini_atlamaz(value, is_valid):
    schema = _field_schema({"type": ["string", "null"], "enum": ["allowed", None]})

    assert (validate_arguments(schema, {"value": value}) == ()) is is_valid


@pytest.mark.parametrize(("value", "is_valid"), [(2, True), (9, False), (1.5, True)])
def test_maximum_ust_siniri_dogrular(value, is_valid):
    schema = _field_schema({"type": ["number", "null"], "maximum": 2})

    assert (validate_arguments(schema, {"value": value}) == ()) is is_valid


@pytest.mark.parametrize("kind", ["object", ["object", "null"]])
def test_kapali_nesne_ek_alanlari_reddeder(kind):
    schema = {
        "parameters": {
            "type": "object",
            "properties": {
                "value": {
                    "type": kind,
                    "properties": {"name": {"type": "string"}},
                    "additionalProperties": False,
                }
            },
        }
    }

    assert validate_arguments(schema, {"value": {"name": "a"}}) == ()
    errors = validate_arguments(schema, {"value": {"name": "a", "extra": 1}})
    assert errors
    assert any("arguments.value.extra" in error for error in errors)


def test_ozellik_tanimlamayan_kapali_nesne_tum_alanlari_reddeder():
    schema = {"parameters": {"type": "object", "additionalProperties": False}}

    assert validate_arguments(schema, {}) == ()
    assert validate_arguments(schema, {"extra": 1})


def test_birlesik_nesne_turu_zorunlu_alan_ve_alt_alan_tipini_dogrular():
    schema = _field_schema(
        {
            "type": ["object", "null"],
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
    )

    assert validate_arguments(schema, {"value": None}) == ()
    assert validate_arguments(schema, {"value": {"name": "a"}}) == ()
    assert validate_arguments(schema, {"value": {}})
    assert validate_arguments(schema, {"value": {"name": 1}})


def test_birlesik_dizi_turu_oge_semasini_dogrular():
    schema = _field_schema({"type": ["array", "null"], "items": {"type": "integer"}})

    assert validate_arguments(schema, {"value": None}) == ()
    assert validate_arguments(schema, {"value": [1]}) == ()
    assert validate_arguments(schema, {"value": ["1"]})

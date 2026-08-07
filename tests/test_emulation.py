"""Taklit araç çağrısı: format, ayrıştırma, doğrulama, eval ve policy."""

from __future__ import annotations

from fusion_cli.config.tool_policy import can_be_mutation_agent
from fusion_cli.core.model_capability import ModelCapability, ToolSupport
from fusion_cli.tools.emulation import (
    CALL_CLOSE,
    CALL_OPEN,
    parse_tool_calls,
    render_call,
    render_tool_instructions,
    validate_arguments,
)
from fusion_cli.tools.emulation_eval import EvalCase, Thresholds, score_emulation

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "edit_file",
        "description": "dosya düzenle",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
}


def _call(name, args):

    return render_call({"name": name, "arguments": args})


# --- render + parse -------------------------------------------------------- #


def test_talimat_arac_adlarini_icerir():
    metin = render_tool_instructions([_SCHEMA])
    assert "edit_file" in metin
    assert CALL_OPEN in metin


def test_gecerli_blok_cagriya_ayristirilir():
    parse = parse_tool_calls(_call("edit_file", {"path": "a.py", "content": "x"}))
    assert len(parse.calls) == 1
    assert parse.calls[0].name == "edit_file"


def test_dogal_metin_cagri_sayilmaz():
    parse = parse_tool_calls("Sadece açıklama yapıyorum, araç yok.")
    assert parse.calls == ()
    assert "açıklama" in parse.text


def test_blok_disi_metin_nihai_cevap_olur():
    parse = parse_tool_calls("Önce şunu düşündüm. " + _call("edit_file", {"path": "a"}))
    assert "düşündüm" in parse.text
    assert len(parse.calls) == 1


def test_bozuk_json_hata_dondurur_sahte_cagri_uretmez():
    parse = parse_tool_calls(f"{CALL_OPEN}\n{{bozuk json\n{CALL_CLOSE}")
    assert parse.calls == ()
    assert len(parse.errors) == 1
    assert "JSON" in parse.errors[0]


def test_name_eksik_blok_reddedilir():
    parse = parse_tool_calls(f'{CALL_OPEN}\n{{"arguments": {{}}}}\n{CALL_CLOSE}')
    assert parse.calls == ()
    assert "name" in parse.errors[0]


def test_coklu_cagri_ayristirilir():
    metin = _call("a", {}) + "\n" + _call("b", {})
    assert len(parse_tool_calls(metin).calls) == 2


# --- doğrulama ------------------------------------------------------------- #


def test_gecerli_argumanlar_hatasiz():
    assert validate_arguments(_SCHEMA["function"], {"path": "a", "content": "x"}) == ()


def test_eksik_zorunlu_alan_hata_verir():
    hatalar = validate_arguments(_SCHEMA["function"], {"path": "a"})
    assert hatalar != ()


def test_semasiz_arac_dogrulamayi_atlar():
    assert validate_arguments({"name": "x"}, {"herhangi": 1}) == ()


# --- eval ------------------------------------------------------------------ #


def test_mukemmel_model_esikleri_gecer():
    cases = [
        EvalCase(
            _call("edit_file", {"path": "a", "content": "x"}),
            "edit_file",
            {"path": "a", "content": "x"},
            _SCHEMA["function"],
        ),
        EvalCase("sadece cevap", None),
    ]
    skor = score_emulation(cases)
    assert skor.passes() is True


def test_yanlis_arac_seciminde_esik_gecilmez():
    cases = [EvalCase(_call("wrong_tool", {}), "edit_file")]
    skor = score_emulation(cases)
    assert skor.tool_selection == 0.0
    assert skor.passes() is False


def test_sahte_cagri_no_false_calls_dusurur():
    # Araç beklenmezken çağrı üretmek: sahte çağrı.
    cases = [EvalCase(_call("edit_file", {}), None)]
    skor = score_emulation(cases)
    assert skor.no_false_calls == 0.0


def test_esikler_yapilandirilabilir():
    gevsek = Thresholds(
        tool_selection=0.0, schema_validity=0.0, argument_preservation=0.0, no_false_calls=0.0
    )
    assert score_emulation([EvalCase(_call("x", {}), "y")]).passes(gevsek) is True


# --- policy ---------------------------------------------------------------- #


def test_emulated_dogrulanmadan_mutation_yapamaz():
    cap = ModelCapability(tool_support=ToolSupport.EMULATED)
    assert can_be_mutation_agent(cap).ok is False


def test_emulated_dogrulaninca_mutation_yapabilir():
    cap = ModelCapability(tool_support=ToolSupport.EMULATED)
    assert can_be_mutation_agent(cap, emulated_verified=True).ok is True

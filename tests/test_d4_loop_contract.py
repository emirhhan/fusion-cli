"""Araç sözleşmesi: bilinmeyen araç önerisi ve gevşek argüman ayrıştırma (A2-05, A2-06, A2-07)."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import Tool, ToolResult
from fusion_cli.engines.agent.loop_contract import (
    _parse_arguments_checked,
    _suggested_tool_schema,
    _tool_contract_failure,
)
from fusion_cli.tools import ToolRegistry


async def _bos(args, context):
    return ToolResult("ok")


def _kayit(*adlar: str) -> ToolRegistry:
    kayit = ToolRegistry()
    for ad in adlar:
        kayit.register(
            Tool(name=ad, description=ad, parameters={"type": "object", "properties": {}}, run=_bos)
        )
    return kayit


def _ornek_adi(metin: str) -> str:
    return metin.split("valid_example:", 1)[1] if "valid_example:" in metin else ""


def test_bilinmeyen_arac_listedeki_son_arac_ornegi_gostermez():
    kayit = _kayit("read_file", "grep", "zz_rastgele_mcp")
    hata = "bilinmeyen araç; kullanılabilir araçlar: " + ", ".join(kayit.names())

    cikti = _tool_contract_failure("bash", [hata], None, registry=kayit)

    assert "zz_rastgele_mcp" not in _ornek_adi(cikti)


def test_bilinmeyen_arac_en_yakin_adin_ornegini_verir():
    kayit = _kayit("read_file", "grep", "zz_rastgele_mcp")
    hata = "bilinmeyen araç; kullanılabilir araçlar: " + ", ".join(kayit.names())

    cikti = _tool_contract_failure("read_fil", [hata], None, registry=kayit)

    assert "read_file" in _ornek_adi(cikti)


def test_arac_adi_sozcuk_icinde_gecince_oneri_olmaz():
    kayit = _kayit("git", "glob", "write_file")

    assert _suggested_tool_schema("write_file", ["global digit thread"], kayit) is None


def test_arac_adi_sozcuk_siniriyla_gecince_onerilir():
    kayit = _kayit("glob", "write_file")

    sema = _suggested_tool_schema("write_file", ["önce glob ile bak"], kayit)

    assert sema is not None and sema["name"] == "glob"


@pytest.mark.parametrize(
    ("ham", "beklenen"),
    [
        ("", {}),
        ("   ", {}),
        ('"{\\"a\\": 1}"', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('{"a": 1, "b": [1, 2,],}', {"a": 1, "b": [1, 2]}),
        ("{'a': 1}", {"a": 1}),
    ],
)
def test_gevsek_arguman_bicimleri_kurtarilir(ham, beklenen):
    arguman, hata = _parse_arguments_checked(ham)
    assert hata is None and arguman == beklenen


def test_kurtarilamayan_arguman_hata_verir():
    arguman, hata = _parse_arguments_checked("{bozuk")
    assert arguman == {} and hata is not None


def test_dizi_arguman_nesne_degil_diye_reddedilir():
    _, hata = _parse_arguments_checked("[1, 2]")
    assert hata is not None


def test_traceback_ilk_satiri_farkli_hatalari_ayni_imzaya_indirmez():
    from fusion_cli.engines.agent.loop_contract import _failure_signature

    bir = "Traceback (most recent call last):\n  File 'a.py'\nKeyError: 'x'"
    iki = "Traceback (most recent call last):\n  File 'b.py'\nValueError: boş"

    assert _failure_signature(bir) != _failure_signature(iki)
    assert _failure_signature(bir) == "KeyError: 'x'"


def test_ayni_hata_ayni_imzayi_verir():
    from fusion_cli.engines.agent.loop_contract import _failure_signature

    assert _failure_signature("Error:\nENOENT dosya yok") == _failure_signature(
        "Error:\nENOENT dosya yok"
    )


def test_ozel_ilk_satir_imza_olarak_kalir():
    from fusion_cli.engines.agent.loop_contract import _failure_signature

    assert _failure_signature("Dosya bulunamadı: a.py\nÖneri: list_dir kullan") == (
        "Dosya bulunamadı: a.py"
    )

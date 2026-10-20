"""Sözleşme hatası, önerdiği aracın örneğini göstermeli.

Ölçüldü (13 Eylül, Godot koşusu): `write_file` mevcut dosyada reddedildi, hata
başka bir aracı önerdi ama örnek yine `write_file` çağrısıydı. Model örneği
izleyip aynı çağrıyı tekrarladı; adım bütçesi doldu ve oyun yarım kaldı.
"""

from __future__ import annotations

from fusion_cli.engines.agent.loop import _tool_contract_failure
from fusion_cli.tools import build_registry

MEVCUT_DOSYA_HATASI = (
    "'project.godot' zaten var. Var olan dosyayı toptan yeniden yazma — önce "
    "read_file ile ilgili satırları gör, sonra edit_file ile YALNIZCA ilgili "
    "satırları değiştir."
)


def _write_file_schema() -> dict[str, object]:
    tool = build_registry().get("write_file")
    assert tool is not None
    schema = tool.schema()["function"]
    assert isinstance(schema, dict)
    return schema


def test_baska_arac_onerildiginde_ornek_o_araca_ait_olur():
    metin = _tool_contract_failure(
        "write_file",
        [MEVCUT_DOSYA_HATASI],
        _write_file_schema(),
        registry=build_registry(),
    )

    ornek = metin.split("valid_example:", 1)[1]
    assert '"name":"edit_file"' in ornek.replace(" ", "")
    assert '"name":"write_file"' not in ornek.replace(" ", "")


def test_arguman_hatasinda_ornek_cagrilan_aracin_kalir():
    """Sorun aracın kendisi değil argümanıysa örnek değişmez."""
    metin = _tool_contract_failure(
        "write_file",
        ["arguments.path: zorunlu alan eksik"],
        _write_file_schema(),
        registry=build_registry(),
    )

    ornek = metin.split("valid_example:", 1)[1]
    assert '"name":"write_file"' in ornek.replace(" ", "")


def test_kayit_defteri_yoksa_davranis_degismez():
    metin = _tool_contract_failure(
        "write_file", [MEVCUT_DOSYA_HATASI], _write_file_schema(), registry=None
    )

    ornek = metin.split("valid_example:", 1)[1]
    assert '"name":"write_file"' in ornek.replace(" ", "")


def test_hata_metni_ve_arac_adi_korunur():
    metin = _tool_contract_failure(
        "write_file", [MEVCUT_DOSYA_HATASI], _write_file_schema(), registry=build_registry()
    )

    assert metin.startswith("TOOL_CALL_INVALID\ntool: write_file")
    assert "zaten var" in metin

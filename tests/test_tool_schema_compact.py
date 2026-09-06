"""Araç şeması zayıf modele göre sadeleşir.

Kısıtlı çözümleme küçük modellerde araç seçimini %49,5'ten %78,1'e çıkarıyor; katı
ve şişkin şema ise "kısıt vergisi" doğuruyor. Web yolunda çağrı METİNDEN üretildiği
için modele gösterilen şema doğrudan başarı oranıdır: opsiyonel alan kalabalığı
zorunlu alanı gölgeler.
"""

from __future__ import annotations

from fusion_cli.core.tool_emulation import render_tool_instructions

_SEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Dosyayı oku.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Yol"},
                    "offset": {"type": "integer", "description": "Başlangıç satırı"},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    }
]


def test_sade_bicimde_yalniz_zorunlu_alanlar_gosterilir():
    metin = render_tool_instructions(_SEMA, compact=True)

    assert '"path"' in metin
    assert "offset" not in metin
    assert "limit" not in metin


def test_sade_bicim_arac_adini_ve_aciklamasini_korur():
    metin = render_tool_instructions(_SEMA, compact=True)

    assert "read_file" in metin
    assert "Dosyayı oku." in metin


def test_varsayilan_bicim_degismez():
    metin = render_tool_instructions(_SEMA)

    assert "offset" in metin
    assert "limit" in metin


def test_zorunlu_alani_olmayan_arac_sade_bicimde_kaybolmaz():
    sema = [
        {
            "type": "function",
            "function": {
                "name": "list_dir",
                "description": "Dizini listele.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        }
    ]

    metin = render_tool_instructions(sema, compact=True)

    assert "list_dir" in metin
    assert '"path"' in metin

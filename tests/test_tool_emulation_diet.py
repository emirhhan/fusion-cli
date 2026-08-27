from __future__ import annotations

from fusion_cli.core.tool_emulation import (
    CALL_CLOSE,
    CALL_OPEN,
    PAYLOAD_SENTINEL,
    render_tool_instructions,
)
from fusion_cli.tools.builtin import build_registry


def rendered() -> str:
    return render_tool_instructions(build_registry().schemas())


def test_emulated_tool_prompt_budgeti():
    text = rendered()

    # Diet öncesi ölçüm: 14_595 karakter.
    assert len(text) <= 10_500


def test_her_tool_icin_generated_ornek_tekrarlanmaz():
    text = rendered()

    assert "kısa değer örneği:" not in text

    # Artık yalnız üç kanonik frame var:
    # kısa çağrı + payload/write + replace_range.
    assert text.count(CALL_OPEN) == 6
    assert text.count(CALL_CLOSE) == 3


def test_schema_yapisi_korunur_description_tekrari_atilir():
    text = rendered()

    assert '"required":["path","start_line","end_line","new"]' in text
    assert '"type":"integer"' in text
    assert '"enum":["pending","in_progress","completed"]' in text

    # Property description metadata'sı emulation promptuna tekrar basılmaz.
    assert '"description":' not in text


def test_payload_ve_range_edit_sozlesmesi_korunur():
    text = rendered()

    assert PAYLOAD_SENTINEL in text
    assert "FUSION_PAYLOAD" in text
    assert "replace_range" in text
    assert "read_file" in text
    assert "yalnız YENİ içeriği gönder" in text


def test_tum_registry_toollari_promptta_hala_var():
    text = rendered()

    for schema in build_registry().schemas():
        function = schema.get("function", {})
        name = function.get("name")

        if name:
            assert f"- {name}:" in text

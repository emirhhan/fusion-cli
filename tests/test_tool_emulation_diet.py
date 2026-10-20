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


#: Emülasyon istemi bütçesi. Diet öncesi ölçüm 14_595; diet sonrası 10_500. 8 Ekim 2026:
#: run_shell teslim kanıtı parametreleri (expected_outputs, failure_check/sources) +157
#: karakter getirdi ve kanıt için gerekli; bütçe yalnız o kadar büyütüldü. Remotion
#: araçları (+1.300) ise yalnız Remotion isteğinde sunulur (`SCOPED_TOOLS`).
# 18 Ekim 2026: chrome_action'a double_click/right_click/drag/wheel (+44 karakter) eklendi;
# arka plan masaüstü araçları ise yalnız masaüstü isteğinde sunulur (`SCOPED_TOOLS`).
PROMPT_BUDGET = 10_760


def test_emulated_tool_prompt_budgeti():
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _permitted

    registry = build_registry()
    sirada = _permitted(None, registry, ExecutionPolicy(is_web=False))
    assert len(render_tool_instructions(registry.schemas(sirada))) <= PROMPT_BUDGET


def test_her_tool_icin_generated_ornek_tekrarlanmaz():
    text = rendered()

    assert "kısa değer örneği:" not in text

    # Artık yalnız üç kanonik frame var:
    # kısa çağrı + payload/write + edit_file.
    assert text.count(CALL_OPEN) == 6
    assert text.count(CALL_CLOSE) == 3


def test_schema_yapisi_korunur_description_tekrari_atilir():
    text = rendered()

    assert '"required":["path","old","new"]' in text
    assert '"type":"integer"' in text
    assert '"enum":["pending","in_progress","completed"]' in text

    # Property description metadata'sı emulation promptuna tekrar basılmaz.
    assert '"description":' not in text


def test_payload_ve_tam_metin_edit_sozlesmesi_korunur():
    text = rendered()

    assert PAYLOAD_SENTINEL in text
    assert "FUSION_PAYLOAD" in text
    assert "edit_file" in text
    assert "read_file" in text
    assert "BİREBİR ve BENZERSİZ" in text


def test_tum_registry_toollari_promptta_hala_var():
    text = rendered()

    for schema in build_registry().schemas():
        function = schema.get("function", {})
        name = function.get("name")

        if name:
            assert f"- {name}:" in text


def test_remotion_araclari_yalniz_remotion_isteginde_sunulur():
    """Ölçüldü (8 Ekim 2026): Codex'in üç Remotion aracı (~1.300 karakter) her istekte
    emülasyon istemine giriyordu; bütçe 10.500'den 11.943'e çıktı. Ücretsiz küçük modelde
    istem uzunluğu kalitedir; araç yalnız ilgili istekte sunulur."""
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import SCOPED_TOOLS, _permitted

    registry = build_registry()
    politika = ExecutionPolicy(is_web=False)
    sirada = _permitted(None, registry, politika)
    assert sirada is not None and not (set(SCOPED_TOOLS) & sirada)
    remotion = _permitted(None, registry, politika, frozenset({"remotion"}))
    remotion_araclari = {ad for ad, tur in SCOPED_TOOLS.items() if tur == "remotion"}
    assert remotion is not None and remotion_araclari <= remotion
    assert not ({ad for ad, tur in SCOPED_TOOLS.items() if tur == "masaustu"} & remotion)

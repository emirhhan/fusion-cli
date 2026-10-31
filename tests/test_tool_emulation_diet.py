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
# 30 Ekim 2026 (T1-40): chrome_action şeması eylem `enum`'u ve her eylem için `value` anlamını
# taşır (+~600 karakter). Zayıf modeller bu bilgiyi yalnız başarısızlık mesajlarından öğreniyor ve
# her model aynı deneme-yanılma turlarını yaşıyordu; tek seferlik bütçe artışı turdan tasarruf eder.
# 31 Ekim 2026 (P-057): salt-okunur `gh` aracı eklendi (+~200 karakter; açıklaması zaten en
# kısa hâlinde). Ölçüldü (dalda): 11_605.
# 31 Ekim 2026 (P-042/043/044/073): chrome_action'a console/network/record/shortcut/window/group
# eylemleri ve chrome_page'e tree/depth/ref parametreleri eklendi (ölçüldü: 11_400 → 11_818,
# +418 karakter). Açıklamalar kısaltıldı; kalan artış eylem adları ve değer biçimleridir.
# 31 Ekim 2026 (parite birleştirmesi): masaüstü fare/klavye/ekran araçları (P-030…P-032),
# Kit araçları (P-063) ve yukarıdaki chrome eylemleri TAM yüzeyi 14_458'e çıkardı. Bu
# yüzey güçlü modele gider; zayıf/web modelin gördüğü kompakt yüzey `desktop_*`/`chrome_*`
# ailesini gizler ve ayrı, daha sıkı bütçeyle korunur (`COMPACT_PROMPT_BUDGET`, ölçüldü 9_623).
PROMPT_BUDGET = 14_600
COMPACT_PROMPT_BUDGET = 10_000


def test_kompakt_yuzey_istemi_zayif_model_butcesinde_kalir():
    from dataclasses import replace

    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.loop import _permitted

    registry = build_registry()
    kompakt = replace(ExecutionPolicy(is_web=False), compact_tool_surface=True)
    sirada = _permitted(None, registry, kompakt)
    assert len(render_tool_instructions(registry.schemas(sirada))) <= COMPACT_PROMPT_BUDGET


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

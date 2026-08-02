"""Araç desteği politikası — araçsız model mutation agent olamaz.

Master prompt §5.3'ün güvenlik kuralı: NONE/EMULATED model dosya değiştiren agent
olamaz; yönlendirme onu seçse bile varsayılan agent rolüne düşülür.
"""

from __future__ import annotations

from fusion_cli.config.eligibility import capability_from_spec
from fusion_cli.config.model_select import select_agent_spec
from fusion_cli.config.tool_policy import can_be_mutation_agent
from fusion_cli.core.model_capability import ModelCapability, ToolSupport
from fusion_cli.core.types import ModelSpec

from .fakes import make_config

# --- politika ------------------------------------------------------------- #


def test_araçsiz_model_mutation_agent_olamaz():
    sonuc = can_be_mutation_agent(ModelCapability(tool_support=ToolSupport.NONE))
    assert sonuc.ok is False
    assert "araç desteği yok" in sonuc.reason


def test_taklit_araç_eval_gecmeden_mutation_yapamaz():
    sonuc = can_be_mutation_agent(ModelCapability(tool_support=ToolSupport.EMULATED))
    assert sonuc.ok is False
    assert "eval" in sonuc.reason


def test_native_model_mutation_yapabilir():
    assert can_be_mutation_agent(ModelCapability(tool_support=ToolSupport.NATIVE)).ok is True


def test_bilinmeyen_model_mutation_yapabilir():
    # UNKNOWN engellenmiyor: araçlarla denenir, desteklemeyen parametre zaten düşer.
    assert can_be_mutation_agent(ModelCapability(tool_support=ToolSupport.UNKNOWN)).ok is True


# --- capability etiket türetimi ------------------------------------------- #


def _spec(*tags):
    return ModelSpec(name="m", model="p/m", tags=tuple(tags))


def test_no_tools_etiketi_none_verir():
    assert capability_from_spec(_spec("code", "no-tools")).tool_support is ToolSupport.NONE


def test_emulated_tools_etiketi_emulated_verir():
    assert capability_from_spec(_spec("emulated-tools")).tool_support is ToolSupport.EMULATED


def test_acik_beyan_ortuk_cikarimi_ezer():
    # Hem "agent" (native ima) hem "no-tools" varsa açık beyan (no-tools) kazanır.
    assert capability_from_spec(_spec("agent", "no-tools")).tool_support is ToolSupport.NONE


# --- select_agent_spec guard ---------------------------------------------- #


def test_araçsiz_adaya_yonlendirme_varsayilan_agenta_duser():
    config = make_config(
        candidates=(
            ModelSpec(name="araçsiz", model="p/chat", tags=("no-tools",)),
            ModelSpec(name="a", model="p/a", tags=("agent",)),
        ),
        task_model_map={"code": "araçsiz"},
    )
    secilen = select_agent_spec(config, "code")
    # Araçsız aday agent olamaz → varsayılan agent rolüne düşülür.
    assert secilen.model == config.agent.model


def test_araç_yetenekli_adaya_yonlendirme_korunur():
    config = make_config(
        candidates=(ModelSpec(name="kodcu", model="p/coder", tags=("agent",)),),
        task_model_map={"code": "kodcu"},
    )
    secilen = select_agent_spec(config, "code")
    assert secilen.model == "p/coder"

"""Model yeteneği türetimi ve profil uygunluğu.

Saf ve offline: etiket + bağlam penceresinden yetenek türetilir, eşiklerle süzülür.
Uydurma yok — yalnızca gerçek sinyaller ve "bilinen-kötüyü ele" kuralı test edilir.
"""

from __future__ import annotations

import pytest

from fusion_cli.config.eligibility import (
    capability_from_spec,
    eligible_profiles,
    is_eligible,
)
from fusion_cli.config.loader import load_config
from fusion_cli.config.models import ProfileEligibility
from fusion_cli.core.model_capability import ModelCapability, ToolSupport
from fusion_cli.core.types import ModelSpec


def _spec(*tags):
    return ModelSpec(name="m", model="p/m", tags=tuple(tags))


def test_agent_etiketi_native_arac_destegi_verir():
    cap = capability_from_spec(_spec("code", "agent"))
    assert cap.tool_support is ToolSupport.NATIVE


def test_agent_etiketsiz_model_bilinmeyen_arac_destegi():
    cap = capability_from_spec(_spec("reasoning", "general"))
    assert cap.tool_support is ToolSupport.UNKNOWN


def test_reasoning_etiketi_reasoning_beyani():
    assert capability_from_spec(_spec("reasoning", "code")).reasoning is True
    assert capability_from_spec(_spec("code")).reasoning is False


def test_baglam_penceresi_disaridan_gelir():
    assert capability_from_spec(_spec("code"), context_window=131072).context_window == 131072
    assert capability_from_spec(_spec("code")).context_window == 0


def test_araçsiz_model_mutation_profiline_giremez():
    cap = ModelCapability(tool_support=ToolSupport.NONE)
    req = ProfileEligibility(min_context=0, allow_no_tools=False)
    sonuc = is_eligible(cap, req)
    assert sonuc.ok is False
    assert "araç" in sonuc.reason


def test_araçsiz_model_low_profilinde_gecerli():
    cap = ModelCapability(tool_support=ToolSupport.NONE)
    req = ProfileEligibility(min_context=0, allow_no_tools=True)
    assert is_eligible(cap, req).ok is True


def test_bilinen_kucuk_baglam_elenir():
    cap = ModelCapability(tool_support=ToolSupport.NATIVE, context_window=32000)
    req = ProfileEligibility(min_context=128000, allow_no_tools=False)
    sonuc = is_eligible(cap, req)
    assert sonuc.ok is False
    assert "bağlam" in sonuc.reason


def test_bilinmeyen_baglam_elenmez():
    # Bağlam 0 (bilinmiyor): eşik olsa bile GİZLENMEZ (gerçekçilik kuralı).
    cap = ModelCapability(tool_support=ToolSupport.NATIVE, context_window=0)
    req = ProfileEligibility(min_context=128000, allow_no_tools=False)
    assert is_eligible(cap, req).ok is True


def test_yeterli_baglam_gecerli():
    cap = ModelCapability(tool_support=ToolSupport.NATIVE, context_window=200000)
    req = ProfileEligibility(min_context=128000, allow_no_tools=False)
    assert is_eligible(cap, req).ok is True


def test_eligible_profiles_uygun_profilleri_dondurur():
    eligibility = {
        "low": ProfileEligibility(min_context=0, allow_no_tools=True),
        "medium": ProfileEligibility(min_context=0, allow_no_tools=False),
        "high": ProfileEligibility(min_context=128000, allow_no_tools=False),
    }
    araçsiz = ModelCapability(tool_support=ToolSupport.NONE)
    assert eligible_profiles(araçsiz, eligibility) == ("low",)
    guclu = ModelCapability(tool_support=ToolSupport.NATIVE, context_window=200000)
    assert eligible_profiles(guclu, eligibility) == ("low", "medium", "high")


@pytest.fixture
def config(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return load_config(hedef)


def test_varsayilan_eslik_esikleri_yuklenir(config):
    assert set(config.profile_eligibility) == {"low", "medium", "high", "max"}
    assert config.profile_eligibility["low"].allow_no_tools is True
    assert config.profile_eligibility["medium"].allow_no_tools is False
    assert config.profile_eligibility["high"].min_context == 128000

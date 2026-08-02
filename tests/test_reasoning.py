"""Reasoning effort — eşleme, model-gating ve sağlayıcıya iletim.

Effort mode'dan AYRIDIR; desteklenmeyen modelde parametre gönderilmez.
"""

from __future__ import annotations

from fusion_cli.config.eligibility import effort_for_spec as _effort_for
from fusion_cli.core.reasoning import (
    ReasoningEffort,
    is_downgraded,
    provider_value,
)
from fusion_cli.core.types import ModelSpec


def test_auto_parametre_gondermez():
    assert provider_value(ReasoningEffort.AUTO) is None


def test_dogrudan_seviyeler_kendine_eslenir():
    assert provider_value(ReasoningEffort.LOW) == "low"
    assert provider_value(ReasoningEffort.MEDIUM) == "medium"
    assert provider_value(ReasoningEffort.HIGH) == "high"


def test_xhigh_ve_max_en_yakina_iner():
    assert provider_value(ReasoningEffort.XHIGH) == "high"
    assert provider_value(ReasoningEffort.MAX) == "high"


def test_indirgeme_isareti():
    assert is_downgraded(ReasoningEffort.XHIGH) is True
    assert is_downgraded(ReasoningEffort.MAX) is True
    assert is_downgraded(ReasoningEffort.HIGH) is False
    assert is_downgraded(ReasoningEffort.AUTO) is False


def test_reasoning_modelde_effort_uygulanir():
    spec = ModelSpec(name="m", model="p/m", tags=("code", "agent", "reasoning"))
    assert _effort_for(spec, ReasoningEffort.HIGH) == "high"


def test_reasoning_desteklemeyen_modelde_effort_dusurulur():
    # reasoning etiketi yok → model reasoning desteklemiyor → parametre gönderilmez.
    spec = ModelSpec(name="m", model="p/m", tags=("code", "agent"))
    assert _effort_for(spec, ReasoningEffort.HIGH) is None


def test_reasoning_modelde_auto_yine_de_none():
    spec = ModelSpec(name="m", model="p/m", tags=("reasoning",))
    assert _effort_for(spec, ReasoningEffort.AUTO) is None

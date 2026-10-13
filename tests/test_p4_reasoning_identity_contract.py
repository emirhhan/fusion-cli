"""P4 independent regression contracts for reasoning capability identity."""
from fusion_cli.core.model_capability import ModelCapability
from fusion_cli.core.reasoning import resolve_reasoning
from fusion_cli.core.types import ModelSpec

def test_unknown_effort_is_not_sent():
    result = resolve_reasoning("high", ModelCapability())
    assert result.requested == "high"
    assert result.applied is None
    assert result.reason

def test_verified_unsupported_is_distinct_from_unknown():
    unknown = resolve_reasoning("low", ModelCapability())
    unsupported = resolve_reasoning("low", ModelCapability(reasoning_efforts_verified=True))
    assert unknown.applied is unsupported.applied is None
    assert unknown.reason != unsupported.reason

def test_higher_effort_fallback_only_to_supported_high():
    supported = ModelCapability(supported_reasoning_efforts=("low", "high"), reasoning_efforts_verified=True)
    assert resolve_reasoning("max", supported).applied == "high"
    assert resolve_reasoning("xhigh", supported).applied == "high"
    assert resolve_reasoning("medium", supported).applied is None

def test_exact_xhigh_is_preserved_when_verified():
    supported = ModelCapability(supported_reasoning_efforts=("xhigh",), reasoning_efforts_verified=True)
    assert resolve_reasoning("xhigh", supported).applied == "xhigh"
    assert resolve_reasoning("auto", supported).applied is None

def test_new_model_drops_old_evidence():
    a = ModelSpec(name="chosen", model="openrouter/A", supported_reasoning_efforts=("high",), reasoning_efforts_verified=True)
    assert a.with_identity("openrouter/A") is a
    b = a.with_identity("openrouter/B")
    assert b.model == "openrouter/B"
    assert b.supported_reasoning_efforts == ()
    assert b.reasoning_efforts_verified is False
    assert a.reasoning_efforts_verified is True

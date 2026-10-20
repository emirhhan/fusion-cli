"""Doğrulanmış yoğunluk değerleri ve bilinmeyen/desteksiz ayrımı."""

from __future__ import annotations

import pytest

from fusion_cli.core.model_capability import ModelCapability
from fusion_cli.core.reasoning import resolve_reasoning


@pytest.mark.parametrize(
    "requested,supported,verified,expected",
    [
        ("high", (), False, None),
        ("high", (), True, None),
        ("xhigh", ("high", "xhigh"), True, "xhigh"),
        ("max", ("high",), True, "high"),
        ("low", ("high",), True, None),
        ("auto", ("high",), True, None),
    ],
)
def test_only_verified_supported_effort_is_applied(
    requested: str, supported: tuple[str, ...], verified: bool, expected: str | None
) -> None:
    result = resolve_reasoning(
        requested,
        ModelCapability(supported_reasoning_efforts=supported, reasoning_efforts_verified=verified),
    )
    assert result.requested == requested
    assert result.applied == expected
    if expected != requested and requested != "auto":
        assert result.reason


def test_capability_config_roundtrip_preserves_exact_verified_values(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fusion_cli.config import loader, writer
    from fusion_cli.config.keys import ProviderKeys

    path = tmp_path / "config.yaml"
    path.write_text(
        "agent:\n  name: secilen\n  model: nvidia_nim/test\n"
        "  supported_reasoning_efforts: [high, xhigh]\n  reasoning_efforts_verified: true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(loader, "detect", lambda: ProviderKeys(False, True))
    config = loader.load_config(path)
    assert config.agent.supported_reasoning_efforts == ("high", "xhigh")
    assert config.agent.reasoning_efforts_verified
    writer.write_model_section(config, path)
    restored = loader.load_config(path)
    assert restored.agent == config.agent


def test_unknown_and_unsupported_reasons_are_distinct() -> None:
    unknown = resolve_reasoning("high", ModelCapability())
    unsupported = resolve_reasoning("high", ModelCapability(reasoning_efforts_verified=True))
    assert unknown.applied is unsupported.applied is None
    assert unknown.reason != unsupported.reason

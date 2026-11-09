"""Explicit protected acceptance profile does not read user config or credentials."""

from __future__ import annotations

from dataclasses import replace

import pytest
from evals.frozen_engine import ACCEPTANCE_TOOLS, require_protected_profile
from scripts.release_manifest import ROOT
from scripts.release_profile import profile_facts

from fusion_cli.config.loader import _assemble, _deep_merge, _read_yaml


def _profile():
    return _assemble(
        _deep_merge(
            _read_yaml(ROOT / "src/fusion_cli/config/defaults.yaml"),
            _read_yaml(ROOT / "release/acceptance-profile.yaml"),
        ),
        None,
    )


def test_checked_in_profile_is_explicit_and_requires_protection(monkeypatch):
    from fusion_cli.config import loader

    monkeypatch.setattr(loader, "load_config", lambda *args: pytest.fail("user config accessed"))
    monkeypatch.setattr(
        loader, "load_environment", lambda *args: pytest.fail("environment/key loader accessed")
    )
    facts = profile_facts(ROOT / "release/acceptance-profile.yaml")
    config = _profile()
    assert facts["model"] == config.agent.model == "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"
    assert config.runtime.max_tokens == 8192
    assert config.runtime.request_timeout_s == 600
    assert config.runtime.max_retries == 0
    assert config.runtime.self_review is True
    assert config.runtime.reasoning_effort.value == "auto"
    assert len(facts["effective_config_digest"]) == 64
    assert "run_shell" in ACCEPTANCE_TOOLS
    assert not {"run_python", "mcp", "spawn_agent", "start_process"} & ACCEPTANCE_TOOLS
    require_protected_profile(_profile(), platform="darwin")


@pytest.mark.parametrize(
    "field", ["allow_unsandboxed", "filesystem_disabled", "enable_weaker_nested_sandbox"]
)
def test_weakened_profile_cannot_collect_authoritative_observations(field):
    config = _profile()
    config = replace(config, sandbox=replace(config.sandbox, **{field: True}))
    with pytest.raises(ValueError, match="profile"):
        require_protected_profile(config, platform="darwin")


def test_windows_has_no_protected_actor_adapter_yet():
    with pytest.raises(ValueError, match="K29"):
        require_protected_profile(_profile(), platform="win32")

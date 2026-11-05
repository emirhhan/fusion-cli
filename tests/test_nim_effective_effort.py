"""Effort receipts must match the installed NIM mapper's actual serialized body."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from fusion_cli.core.model_capability import ModelCapability
from fusion_cli.providers import litellm_provider
from fusion_cli.providers.litellm_provider import LiteLlmProvider
from tests.fakes import model_result, request


def _receipt(tmp_path, effort, mode, disable=False):
    root = Path(__file__).resolve().parents[1]
    env = {
        "HOME": str(tmp_path),
        "PATH": os.defpath,
        "PYTHONPATH": str(root / "src"),
        "LITELLM_MODE": "PRODUCTION",
        "PYTHON_DOTENV_DISABLED": "1",
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "NVIDIA_NIM_API_BASE": "https://nim-fixture.invalid/v1",
        "NVIDIA_NIM_API_KEY": "synthetic-not-a-real-key",
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "tests/fixtures/nim_effort_transport.py"),
            effort,
            mode,
            "1" if disable else "0",
        ],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(completed.stdout)


@pytest.mark.parametrize("effort", ["low", "high"])
@pytest.mark.parametrize("mode", ["stream", "complete"])
def test_exact_main_dropped_effort_is_not_reported_applied(tmp_path, effort, mode):
    receipt = _receipt(tmp_path, effort, mode)
    assert receipt["leaf_kwargs"]["reasoning_effort"] == effort
    assert "reasoning_effort" not in receipt["wire_bodies"][0]
    metadata = receipt["metadata"]
    assert metadata["ok"] is True
    assert metadata["requested_effort"] == effort
    assert metadata["applied_effort"] is None, "SDK-dropped effort cannot be advertised as applied"
    assert "NIM" in metadata["effort_reason"]
    assert "ilet" in metadata["effort_reason"]


@pytest.mark.parametrize("mode", ["stream", "complete"])
@pytest.mark.parametrize("disable", [False, True])
def test_auto_and_independent_thinking_template_keep_existing_wire_behavior(
    tmp_path, mode, disable
):
    receipt = _receipt(tmp_path, "auto", mode, disable)
    body = receipt["wire_bodies"][0]
    assert "reasoning_effort" not in body
    if disable:
        assert body["chat_template_kwargs"]["enable_thinking"] is False
    else:
        assert "chat_template_kwargs" not in body
    assert receipt["metadata"] == {
        "requested_effort": None,
        "applied_effort": None,
        "effort_reason": "",
        "ok": True,
    }


@pytest.mark.parametrize("model", ["openai/gpt-5", "nvidia_nim_lookalike/model"])
def test_non_nim_receipt_does_not_query_or_change_transport_effort(monkeypatch, model):
    def unexpected_sdk():
        raise AssertionError("Other providers must not enter NIM transport inspection")

    monkeypatch.setattr(litellm_provider, "_litellm", unexpected_sdk)
    provider = LiteLlmProvider(
        model,
        role="fixture",
        capability=ModelCapability(
            supported_reasoning_efforts=("low",),
            reasoning_efforts_verified=True,
        ),
    )
    result = provider._with_effort(model_result("ok"), replace(request(), reasoning_effort="low"))
    assert result.requested_effort == result.applied_effort == "low"
    assert result.effort_reason == ""


@pytest.mark.parametrize("supported", [["reasoning_effort"], None])
def test_nim_receipt_uses_installed_transport_support_without_assuming_model_support(
    monkeypatch,
    supported,
):
    from types import SimpleNamespace

    observed = []

    def params(**kwargs):
        observed.append(kwargs)
        return supported

    monkeypatch.setattr(
        litellm_provider,
        "_litellm",
        lambda: SimpleNamespace(
            get_supported_openai_params=params,
        ),
    )
    provider = LiteLlmProvider(
        "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b",
        role="fixture",
        capability=ModelCapability(
            supported_reasoning_efforts=("low",), reasoning_efforts_verified=True
        ),
    )
    result = provider._with_effort(model_result("ok"), replace(request(), reasoning_effort="low"))
    assert observed == [
        {"model": "nvidia/nemotron-3-ultra-550b-a55b", "custom_llm_provider": "nvidia_nim"}
    ]
    assert result.requested_effort == "low"
    if supported:
        assert result.applied_effort == "low"
        assert result.effort_reason == ""
    else:
        assert result.applied_effort is None
        assert "doğrulanmadı" in result.effort_reason


def test_unverified_nim_effort_keeps_capability_reason_without_sdk_query(monkeypatch):
    def unexpected_sdk():
        raise AssertionError("Unverified capability must not become a transport claim")

    monkeypatch.setattr(litellm_provider, "_litellm", unexpected_sdk)
    provider = LiteLlmProvider("nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b", role="fixture")
    result = provider._with_effort(model_result("ok"), replace(request(), reasoning_effort="low"))
    assert result.requested_effort == "low"
    assert result.applied_effort is None
    assert "desteği doğrulanmadı" in result.effort_reason

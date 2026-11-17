"""NIM must honor the leaf retry setting through installed SDK mapping."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fusion_cli.providers.litellm_provider import LiteLlmProvider

from .fakes import request


@pytest.mark.parametrize(
    ("retries", "mode", "attempts", "ok"),
    [(0, "stream", 1, False), (2, "stream", 3, True), (0, "complete", 1, False)],
)
def test_nim_retry_limit_reaches_sdk_transport(tmp_path, retries, mode, attempts, ok):
    """500/500/200 exposes SDK retries hidden behind a single leaf call."""
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
    result = subprocess.run(
        [sys.executable, str(root / "tests/fixtures/nim_retry_transport.py"), str(retries), mode],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    receipt = json.loads(result.stdout)
    assert receipt["http_requests"] == attempts
    assert receipt["ok"] is ok
    assert receipt["text"] == ("ok" if ok else "")
    assert all(bool(item["stream"]) is (mode == "stream") for item in receipt["requests"])
    assert all(item["max_tokens"] == 16 for item in receipt["requests"])
    assert not any(item["max_retries_in_body"] for item in receipt["requests"])


def test_retry_override_is_not_added_to_other_transports(monkeypatch):
    monkeypatch.setattr("fusion_cli.providers.litellm_provider.ollama_num_ctx", lambda _: 8192)
    for model in ("openai/gpt-4o", "ollama_chat/qwen3:8b", "nvidia_nim_lookalike/model"):
        kwargs = LiteLlmProvider(model, role="agent")._call_kwargs(request(), stream=True)
        assert "allowed_openai_params" not in kwargs

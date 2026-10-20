"""Web ölçümü kimliğe bağlıdır; eski bool kaydı tarih/sürüm kanıtı üretmez."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.config import web_evidence
from fusion_cli.config.models import WebSessionConfig
from fusion_cli.config.tool_policy import mutation_policy_for_model
from fusion_cli.core.types import ModelSpec
from fusion_cli.providers.capabilities import capabilities_for
from fusion_cli.providers.web_control import set_tool_eval_passed

from .fakes import make_config


@pytest.mark.parametrize(
    "changes",
    [
        {"account": "other"},
        {"transport": "http"},
        {"selected_model": "changed"},
        {"provider": "claude_web"},
    ],
)
def test_measured_web_identity_change_invalidates_mutation_authority(
    changes: dict[str, str],
) -> None:
    session = WebSessionConfig(
        model="gemini_web/main/auto",
        provider="gemini_web",
        transport="browser",
        tool_support="emulated",
        tool_eval_passed=False,
    )
    config = make_config(web_sessions=(session,))
    measured = set_tool_eval_passed(config, "gemini_web", "main", True, measured_at=42.0)
    assert measured is not None
    changed = replace(measured.web_sessions[0], **changes)
    stale = replace(measured, web_sessions=(changed,))
    assert not mutation_policy_for_model(stale, changed.model).ok
    assert not capabilities_for(ModelSpec(name="agent", model=changed.model), (changed,)).tools


def test_legacy_permission_preserved_but_no_timestamp_or_version_is_invented() -> None:
    session = WebSessionConfig(
        model="gemini_web/main/auto",
        provider="gemini_web",
        tool_support="emulated",
        tool_eval_passed=True,
    )
    capability = capabilities_for(ModelSpec(name="agent", model=session.model), (session,))
    assert capability.tools
    assert capability.evaluation_state == "legacy-unverified"
    assert capability.last_evaluated_at == 0.0


def test_adapter_revision_changes_when_browser_adapter_changes(tmp_path, monkeypatch) -> None:
    root = tmp_path / "fusion_cli"
    (root / "config").mkdir(parents=True)
    (root / "core").mkdir()
    (root / "providers").mkdir()
    monkeypatch.setattr(web_evidence, "__file__", str(root / "config" / "web_evidence.py"))
    (root / "core" / "tool_emulation.py").write_text("protocol-v1")
    for name in ("web_browser.py", "web_session.py", "web_transport.py"):
        (root / "providers" / name).write_text("adapter-v1")
    before = web_evidence.web_adapter_revision()
    (root / "providers" / "web_browser.py").write_text("adapter-v2")
    assert before
    assert web_evidence.web_adapter_revision() != before

"""Recovery guidance follows authorized effects, not a universal coding workflow."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent import reflexion


@pytest.mark.parametrize("desktop", [False, True])
def test_nonworkspace_recovery_does_not_command_repository_changes(desktop):
    context = reflexion.recovery_context(required_effect=None, desktop=desktop)
    for message in (
        reflexion.note(persistent=False, context=context),
        reflexion.stall_rescue_note(context=context),
    ):
        assert message.harness_note
        assert "read_file" not in message.content
        assert "search_code" not in message.content
        assert "dosyayı" not in message.content
        assert "İLK somut değişikliğini" not in message.content
        assert "engel" in message.content
    if desktop:
        assert "hedef uygulama" in reflexion.stall_rescue_note(context=context).content
        assert "doğrula" in reflexion.note(persistent=False, context=context).content


def test_real_workspace_mutation_keeps_software_progress_guidance_even_with_desktop_context():
    context = reflexion.recovery_context(required_effect="workspace_mutation", desktop=True)
    assert "İLK somut değişikliğini" in reflexion.stall_rescue_note(context=context).content
    assert "read_file / search_code" in reflexion.note(persistent=False, context=context).content


@pytest.mark.parametrize("effect", ["workspace_read", "web_lookup", "git_push", "shell_action"])
def test_other_effects_do_not_authorize_unrequested_workspace_changes(effect):
    context = reflexion.recovery_context(required_effect=effect, desktop=False)
    assert "İLK somut değişikliğini" not in reflexion.stall_rescue_note(context=context).content


@pytest.mark.parametrize("workspace", [False, True])
async def test_drive_routes_error_and_idle_notes_to_the_requested_scope(
    tmp_path, monkeypatch, workspace
):
    from dataclasses import replace

    from fusion_cli.core.tools import ToolResult
    from fusion_cli.engines.agent import loop
    from fusion_cli.tools.builtin import build_registry
    from fusion_cli.tools.registry import ToolRegistry
    from tests.fakes import ScriptedProvider, model_result, tool_call
    from tests.test_agent_lessons import _deps

    deps = _deps(tmp_path)
    deps.config = replace(
        deps.config,
        runtime=replace(deps.config.runtime, agent_max_idle_rounds=1),
    )
    registry = ToolRegistry()
    read = next(tool for tool in build_registry() if tool.name == "read_file")
    registry.register(replace(read, run=lambda args, ctx: ToolResult.failure("Synthetic error")))
    deps.base_registry = registry
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("read_file", path="missing.txt")]),
            model_result("Değer doğrulanamadı; işlem tamamlanmadı."),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    task = (
        "src/app.py dosyasını düzenle."
        if workspace
        else "Masaüstünde Hesap Makinesi uygulamasında 18 × 24 işlemini yap ve değeri doğrula."
    )
    result = await loop.run_agent(
        task,
        deps,
        verify=False,
        self_review=False,
    )
    notes = [m.content for m in result.messages if m.harness_note]
    recovery = [n for n in notes if n.startswith(("[refleksiyon]", "[ilerleme-yok]"))]
    assert any(n.startswith("[refleksiyon]") for n in recovery)
    assert any(n.startswith("[ilerleme-yok]") for n in recovery)
    if workspace:
        assert reflexion.WORKSPACE_NOTE in recovery
        assert reflexion.WORKSPACE_STALL_RESCUE_NOTE in recovery
    else:
        assert all("read_file" not in n and "search_code" not in n for n in recovery)
        assert all("hedef uygulama" in n.lower() for n in recovery)

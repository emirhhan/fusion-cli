"""Gerçek çağrıya giden talimat ölçümü; ham metin olayda taşınmaz."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.loop import run_agent

from .fakes import RecordingSink, ScriptedProvider, model_result
from .test_agent_loop import _deps, _kur


async def test_ilk_talimat_yuku_gercek_cagrinin_manifestine_tasinir(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("Zorunlu orta kural. " * 1000)
    sink = RecordingSink()
    provider = _kur(monkeypatch, ScriptedProvider([model_result("Merhaba.")]))
    deps = _deps(
        tmp_path, sink, runtime={"project_instructions": True, "instruction_max_chars": 500}
    )
    await run_agent("merhaba", deps, chat_mode=True)
    events = [event for event in sink.events if type(event).__name__ == "PromptManifestRecorded"]
    assert events, "Gerçek model çağrısı prompt manifesti yayınlamalı"
    manifest = events[-1].manifest
    # Claude Code (#143): talimat 4 MiB'a kadar kırpılmadan yüklenir.
    assert manifest.instruction_trimmed_chars == 0
    assert any(item.label == "AGENTS.md" for item in manifest.instruction_files)
    assert (
        manifest.total_chars == manifest.system_chars + manifest.history_chars + manifest.tool_chars
    )
    assert "Zorunlu orta kural" not in repr(manifest)
    assert provider.seen_messages


async def test_gercek_web_son_kirpma_orta_kural_kaybini_manifestte_olcer(tmp_path, monkeypatch):
    from fusion_cli.providers import web_browser as browser
    from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn

    sent = []

    class Locator:
        async def click(self):
            pass

        async def press(self, key):
            pass

    async def locator(*args, **kwargs):
        return Locator()

    async def no_login(*args, **kwargs):
        return False

    async def snapshot(*args, **kwargs):
        return ()

    async def attach(*args, **kwargs):
        return 0

    async def fill(locator, text):
        sent.append(text)

    async def answer(*args, **kwargs):
        return "Merhaba."

    monkeypatch.setattr(browser, "_first_visible", locator)
    monkeypatch.setattr(browser, "_strong_login_signal", no_login)
    monkeypatch.setattr(browser, "_response_snapshot", snapshot)
    monkeypatch.setattr(browser, "_attach_images", attach)
    monkeypatch.setattr(browser, "_fill_editor", fill)
    monkeypatch.setattr(browser, "_wait_for_response", answer)

    async def transport(credential, messages, model, **kwargs):
        measured = []
        prompt = browser.format_browser_prompt(messages, trim=False)
        text = await browser._send_turn(
            object(),
            browser.provider_definition("chatgpt_web"),
            prompt,
            measurement_sink=measured.append,
        )
        return WebTurn(text, prompt_measurement=measured[-1])

    adapter = WebProviderAdapter(
        model="sahte/agent", credential=WebSessionCredential(), transport=transport
    )
    _kur(monkeypatch, adapter)
    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    prompt = "baş\n" + "a" * 32000 + "\nZORUNLU-ORTA-KURAL\n" + "b" * 32000 + "\nson"
    await run_agent("merhaba", deps, chat_mode=True, system_prompt=prompt)
    assert sent and "ZORUNLU-ORTA-KURAL" not in sent[-1]
    manifest = [
        event.manifest for event in sink.events if type(event).__name__ == "PromptManifestRecorded"
    ][-1]
    assert manifest.transport.sent_chars == len(sent[-1])
    assert manifest.transport.trimmed_chars > 0
    assert manifest.tokens_estimated
    assert manifest.transport.input_chars > manifest.transport.sent_chars


async def test_manifest_metadata_sirlari_olaydan_once_maskelenir():
    from pathlib import Path

    from fusion_cli.core.types import CompletionRequest, Message, ModelResult, TokenUsage
    from fusion_cli.engines.agent.instruction_layers import InstructionFile, InstructionLoad
    from fusion_cli.engines.agent.prompt_manifest import PromptComponents, publish_manifest

    from .test_agent_loop import _Publisher

    secret = "ghp_" + "Z" * 36
    components = PromptComponents(
        InstructionLoad(
            "", (InstructionFile(secret, Path("x"), "proje", 0, 9, False),), ("Bearer\n" + secret,)
        )
    )
    sink = RecordingSink()
    request = CompletionRequest((Message("user", "gerçek kullanıcı metni"),), 0, 10, 1)
    result = ModelResult(
        "sahte",
        "sahte/model",
        "tamam",
        0,
        True,
        usage=TokenUsage(prompt_tokens=17, prompt_measured=True),
    )
    publish_manifest(request, result, components, _Publisher(sink))
    manifest = sink.events[-1].manifest
    assert secret not in repr(manifest)
    assert manifest.prompt_tokens == 17 and not manifest.tokens_estimated


@pytest.mark.parametrize(
    "profile_provider,profile_model,result_model,expected",
    [
        ("sahte", "sahte/agent", "sahte/agent", "eval-4k"),
        ("sahte", "sahte/other", "sahte/agent", None),
        ("other", "sahte/agent", "sahte/agent", None),
        ("sahte", "sahte/agent", "sahte/fallback", None),
    ],
)
async def test_manifest_gercek_cagrida_yalniz_dogrulanmis_profili_kaydeder(
    tmp_path, monkeypatch, profile_provider, profile_model, result_model, expected
):
    from dataclasses import replace

    from fusion_cli.core.prompt_manifest import ContextProfile
    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.context_budget import context_budget
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.tools import ToolRegistry

    sink = RecordingSink()
    deps = _deps(tmp_path, sink)
    deps.active_model_override = replace(
        deps.config.agent,
        context_profile=ContextProfile("eval-4k", profile_provider, profile_model, 4000),
    )
    _kur(monkeypatch, ScriptedProvider([replace(model_result("yanıt"), model=result_model)]))
    await loop._call_model(
        [Message("user", "merhaba")],
        deps,
        ToolRegistry(),
        state=loop._State(),
        execution=ExecutionPolicy(is_web=False),
        offer_tools=False,
    )
    manifest = [
        event.manifest for event in sink.events if type(event).__name__ == "PromptManifestRecorded"
    ][-1]
    assert manifest.profile == expected
    if result_model == deps.active_model_override.model:
        assert manifest.profile == context_budget(deps.config, deps.active_model_override).profile

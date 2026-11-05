"""Değişmez başlangıç talimatları yumuşak konuşma bütçesini tüketmez."""

import pytest

from fusion_cli.core.errors import ConfigError
from fusion_cli.core.events import ContextCompressed
from fusion_cli.core.model_capability import ToolSupport
from fusion_cli.core.tool_emulation import render_call
from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent import compaction, context_budget, history
from fusion_cli.engines.agent.loop import run_agent
from fusion_cli.engines.agent.project_instructions import load_all_instructions
from fusion_cli.providers.web_session import WebProviderAdapter, WebSessionCredential, WebTurn

from .fakes import RecordingSink
from .test_agent_loop import _deps, _kur


def _instructions(tmp_path):
    home = tmp_path / "home"
    rules = home / ".claude" / "CLAUDE.md"
    rules.parent.mkdir(parents=True)
    rules.write_text("Sentetik kalıcı talimatı birebir koru.\n" * 1500)
    root = tmp_path / "project"
    root.mkdir()
    loaded = load_all_instructions(root, home)
    assert len(loaded.text) > 50_000
    return root, home, loaded.text


@pytest.mark.parametrize("output_chars", [30, 9000])
async def test_real_instruction_loader_web_frames_keep_large_prefix_without_summaries(
    monkeypatch, tmp_path, output_chars
):
    root, home, instructions = _instructions(tmp_path)
    for index in range(4):
        (root / f"sample{index}.txt").write_text("Doğrulanmış küçük dosya. " + "x" * output_chars)
    sent = []

    async def transport(credential, messages, model, *, context):
        sent.append(messages)
        if len(sent) <= 4:
            return WebTurn(
                render_call(
                    {"name": "read_file", "arguments": {"path": f"sample{len(sent) - 1}.txt"}}
                )
            )
        return WebTurn("Dosya okundu: Doğrulanmış küçük dosya.")

    adapter = WebProviderAdapter(
        model="gemini_web/main/auto",
        credential=WebSessionCredential(),
        transport=transport,
        tool_support=ToolSupport.EMULATED,
    )
    _kur(monkeypatch, adapter)
    summaries = []

    async def summarize(*args, **kwargs):
        summaries.append(True)
        return "özet"

    monkeypatch.setattr(compaction, "_summarize", summarize)
    sink = RecordingSink()
    deps = _deps(root, sink, home=home, agent=ModelSpec("agent", "gemini_web/main/auto"))
    result = await run_agent(
        "sample0.txt ile sample3.txt arasındaki dört dosyayı oku ve içeriğini bildir", deps
    )

    assert result.ok and result.final_text.startswith("Dosya okundu:")
    assert result.tool_calls_made == 4
    assert len(sent) == 5
    assert not summaries
    assert bool([event for event in sink.events if isinstance(event, ContextCompressed)]) == (
        output_chars > 30
    )
    assert all(instructions in "\n".join(message.content for message in batch) for batch in sent)
    assert instructions in "\n".join(message.content for message in result.messages)

    continued = await run_agent(
        "Sonucu bir cümleyle yeniden açıkla.",
        _deps(root, sink, home=home, agent=ModelSpec("agent", "gemini_web/main/auto")),
        history=result.messages,
    )
    assert continued.ok and continued.final_text.startswith("Dosya okundu:")
    assert len(sent) == 6
    assert "\n".join(message.content for message in sent[-1]).count(instructions) == 1
    assert not summaries


def test_soft_budget_excludes_exact_compactor_anchor_but_not_tool_history():
    messages = [
        Message("system", "s" * 10_000),
        Message("user", "i" * 50_000, harness_note=True),
        Message("user", "görev"),
        Message("assistant", "v" * 25_000),
    ]
    budget = context_budget.ContextBudget(24_000, None, "web")
    threshold = context_budget.compression_threshold(budget, messages)
    assert threshold == 24_000 + history.history_chars(
        messages[: history.task_anchor_length(messages)]
    )
    assert history.needs_compression(messages, threshold)
    assert not history.needs_compression(messages[:-1], threshold)


@pytest.mark.parametrize("window,learned", [(65_536, None), (None, 20_000)])
def test_immutable_prefix_over_hard_cap_fails_explicitly(window, learned):
    messages = [
        Message("system", "s" * 10_000),
        Message("user", "i" * 200_000, harness_note=True),
        Message("user", "görev"),
    ]
    budget = context_budget.ContextBudget(24_000, window, "model")
    with pytest.raises(ConfigError, match=r"korunan.*bağlam"):
        context_budget.compression_threshold(budget, messages, learned_chars=learned)


@pytest.mark.parametrize("window,learned", [(65_536, None), (None, 65_000), (65_536, 65_000)])
def test_soft_prefix_allowance_never_inflates_known_or_learned_cap(window, learned):
    messages = [
        Message("system", "s" * 10_000),
        Message("user", "i" * 50_000, harness_note=True),
        Message("user", "görev"),
    ]
    budget = context_budget.ContextBudget(24_000, window, "model")
    threshold = context_budget.compression_threshold(budget, messages, learned_chars=learned)
    if window is not None:
        assert threshold <= context_budget.fixed_prefix_cap(10**9, window, 10_000)
    if learned is not None:
        assert threshold <= learned


async def test_volatile_assistant_growth_is_summarized_without_loading_protected_rules(
    monkeypatch, tmp_path
):
    root, home, instructions = _instructions(tmp_path)
    messages = [
        Message("system", "sistem"),
        Message("user", instructions, harness_note=True),
        Message("user", "görev"),
        *[Message("assistant", f"adım {index}: " + "v" * 1000) for index in range(30)],
    ]
    traces = []

    async def summarize(trace, *args, **kwargs):
        traces.append(trace)
        return "Önceki adımların kısa özeti."

    monkeypatch.setattr(compaction, "_summarize", summarize)
    deps = _deps(root, RecordingSink(), home=home)
    threshold = context_budget.compression_threshold(
        context_budget.ContextBudget(24_000, None, "web"), messages
    )
    result = await compaction.compact_in_turn(
        messages, config=deps.config, threshold_chars=threshold
    )
    assert traces and all(len(trace) <= compaction.TRACE_CHARS for trace in traces)
    assert all(instructions not in trace for trace in traces)
    assert result[:3] == messages[:3]
    assert not history.needs_compression(result, threshold)
    assert any(message.content.startswith(history.STEPS_SUMMARY_PREFIX) for message in result)


async def test_impossible_prefix_finishes_desktop_request_and_releases_turn(monkeypatch, tmp_path):
    import asyncio
    import json

    from fusion_cli.appserver.protocol import Request
    from fusion_cli.appserver.session import AppSession

    from .fakes import ScriptedProvider

    root, home, _instructions_text = _instructions(tmp_path)
    provider = _kur(monkeypatch, ScriptedProvider([]))
    monkeypatch.setattr(
        context_budget,
        "context_budget",
        lambda config, spec: context_budget.ContextBudget(24_000, 16_384, spec.model),
    )

    async def execute(task, config, **kwargs):
        return await run_agent(task, _deps(root, RecordingSink(), home=home))

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", execute)
    lines = []
    session = AppSession(lines.append, root=root, home=home)
    try:
        await asyncio.wait_for(
            session.handle(
                Request(
                    id="overflow",
                    name="tur.calistir",
                    data={"gorev": "Dosyaları incele", "gonderim_id": "overflow"},
                )
            ),
            timeout=5,
        )
        response = json.loads(lines[-1])
        assert not response["veri"]["ok"]
        assert "korunan" in response["veri"]["metin"]
        assert provider.calls == 0
        assert session._turn is None and session._turn_settled.is_set()
        assert session._submission_task is None
    finally:
        await session.close()

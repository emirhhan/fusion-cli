"""Gerçek loop, aynı journal üreticisi ve scoped okuyucu üzerinden özetler."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent import compaction, loop
from fusion_cli.memory.turn_journal import FileTurnJournal

from .fakes import RecordingSink
from .test_agent_loop import _deps


async def test_runtime_ozgun_journal_uretir_ve_ozetleyici_gercek_izi_okur(tmp_path, monkeypatch):
    deps = _deps(tmp_path, RecordingSink())
    assert hasattr(deps.config.runtime, "context_original_trace")
    deps.config = replace(
        deps.config, runtime=replace(deps.config.runtime, context_original_trace=True)
    )
    deps.journal = FileTurnJournal(tmp_path / "journal.json", task="iş", original_owner_id="owner")
    deps.attempt_id = "turn"
    deps.learned_compression_chars = 300
    traces = []

    async def summarize(trace, *args):
        traces.append(trace)
        return "Kısa özet."

    monkeypatch.setattr(compaction, "_summarize", summarize)
    messages = [Message("system", "sistem"), Message("user", "iş")]
    for index in range(18):
        call = ToolCall(f"call{index}", "read_file", "{}")
        messages.extend(
            (
                Message("assistant", "", tool_calls=(call,)),
                Message("tool", f"ÖZGÜN-{index} " + "a" * 400, tool_call_id=call.id),
            )
        )
    await loop._compact_before_call(messages, deps, loop._State())
    assert deps.journal.original_path.exists()
    assert traces and "kaynak: maskelenmiş özgün segment" in traces[0]
    assert "ÖZGÜN-0" in traces[0]


async def test_basarisiz_append_kismi_izi_tam_olarak_sunmaz(tmp_path, monkeypatch):
    deps = _deps(tmp_path, RecordingSink())
    deps.config = replace(
        deps.config, runtime=replace(deps.config.runtime, context_original_trace=True)
    )

    class FailingJournal(FileTurnJournal):
        async def append_original(self, scope, messages):
            if messages[0].tool_calls[0].id == "call0":
                return False
            return await super().append_original(scope, messages)

    deps.journal = FailingJournal(tmp_path / "journal.json", task="iş", original_owner_id="owner")
    deps.attempt_id = "turn"
    deps.learned_compression_chars = 300
    traces = []

    async def summarize(trace, *args):
        traces.append(trace)
        return "Kısa özet."

    monkeypatch.setattr(compaction, "_summarize", summarize)
    messages = [Message("system", "sistem"), Message("user", "iş")]
    for index in range(18):
        call = ToolCall(f"call{index}", "read_file", "{}")
        messages.extend(
            (
                Message("assistant", "", tool_calls=(call,)),
                Message("tool", "a" * 400, tool_call_id=call.id),
            )
        )
    await loop._compact_before_call(messages, deps, loop._State())
    assert traces and "özgün iz kullanılamadı" in traces[0]
    assert "kaynak: maskelenmiş özgün segment" not in traces[0]


@pytest.mark.parametrize("between_turns", [False, True])
async def test_cok_turlu_teslim_istegi_uc_sikistirmada_ozetleyiciye_ulasir(
    tmp_path, monkeypatch, between_turns
):
    deps = _deps(tmp_path, RecordingSink())
    deps.config = replace(
        deps.config, runtime=replace(deps.config.runtime, context_original_trace=True)
    )
    deps.journal = FileTurnJournal(tmp_path / "journal.json", task="iş", original_owner_id="owner")
    deps.attempt_id = "turn"
    deps.learned_compression_chars = 300
    requirement = "Teslim hedefi: raporu teslim.csv dosyasına yaz."
    messages = [
        Message("system", "sistem"),
        Message("user", "ilk görev"),
        Message("assistant", "Önceki yanıt."),
        Message("user", requirement),
    ]
    traces = []

    async def summarize(trace, *args):
        traces.append(trace)
        return requirement if requirement in trace else "Özet."

    monkeypatch.setattr(compaction, "_summarize", summarize)
    for cycle in range(3):
        for index in range(18):
            call = ToolCall(f"call-{cycle}-{index}", "read_file", "{}")
            messages.extend(
                (
                    Message("assistant", "", tool_calls=(call,)),
                    Message("tool", "a" * 400, tool_call_id=call.id),
                )
            )
            if between_turns:
                messages.append(Message("user", f"Ek gözlem {cycle}-{index}"))
        if between_turns:
            messages = await loop._maybe_compress(messages, deps)
        else:
            await loop._compact_before_call(messages, deps, loop._State())
        assert requirement in traces[-1]
        assert requirement in "\n".join(message.content for message in messages)
        assert "kaynak: maskelenmiş özgün segment" not in traces[-1]
        assert "özgün iz kullanılamadı" in traces[-1]
    assert len(traces) == 3

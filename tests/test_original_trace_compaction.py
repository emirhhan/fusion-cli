"""Yerel özgün iz temeli: gerçek model veya çalışma döngüsü başarısı ölçülmez."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.original_trace import OriginalTraceRead, OriginalTraceScope
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent import compaction, history
from fusion_cli.memory.turn_journal import FileTurnJournal

from .fakes import make_config


def _steps(count: int) -> list[Message]:
    messages = [Message("system", "kimlik"), Message("user", "incele")]
    for index in range(count):
        call = ToolCall(f"c{index}", "read_file", '{"path":"src/a.py"}')
        messages.extend(
            (
                Message("assistant", "karar " + "x" * 200, tool_calls=(call,)),
                Message("tool", f"kanıt {index}", tool_call_id=call.id),
            )
        )
    return messages


async def _journal(tmp_path, messages):
    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    for index in range(20):
        segment = messages[2 + index * 2 : 4 + index * 2]
        assert await journal.append_original(
            OriginalTraceScope("chat1", "turn1", (f"s{index}",)), segment
        )
    scope = OriginalTraceScope("chat1", "turn1", tuple(f"s{index}" for index in range(20)))
    return journal, scope


async def test_compactor_gercek_segmenti_okur_sikistirilmis_mesaji_ozgun_saymaz(
    tmp_path, monkeypatch
):
    messages = _steps(30)
    messages[2] = replace(messages[2], content="ORIGINAL-PATH src/retained.py")
    messages[3] = replace(messages[3], content="ORIGINAL-RULE Asla uzak sisteme gönderme.")
    journal, scope = await _journal(tmp_path, messages)
    compressed = list(messages)
    compressed[2] = replace(messages[2], content="kayıplı karar")
    compressed[3] = replace(messages[3], content=history.CLEARED_TOOL_OUTPUT.format(chars=100))

    async def summarize(trace, _config, _publisher):
        return trace

    monkeypatch.setattr(compaction, "_summarize", summarize)
    result = await compaction.compact_in_turn(
        compressed,
        config=make_config(),
        threshold_chars=1_000,
        original_source=journal,
        original_scope=scope,
    )
    summary = result[2].content
    assert "ORIGINAL-PATH" in summary and "ORIGINAL-RULE" in summary
    assert "maskelenmiş özgün segment" in summary
    assert result[-20:] == messages[-20:]
    fallback = await compaction.compact_in_turn(
        compressed, config=make_config(), threshold_chars=1_000
    )
    assert "ORIGINAL-PATH" not in fallback[2].content


@pytest.mark.parametrize("change", ["owner", "turn", "missing", "budget", "recent"])
async def test_kapsam_yanlissa_sikistirilmis_gecmise_acik_fallback_yapar(
    tmp_path, monkeypatch, change
):
    messages = _steps(30)
    journal, scope = await _journal(tmp_path, messages)
    if change == "owner":
        scope = replace(scope, owner_id="other")
    elif change == "turn":
        scope = replace(scope, turn_id="other")
    elif change == "missing":
        scope = replace(scope, segment_ids=("absent",))
    elif change == "budget":
        scope = replace(scope, max_chars=10)
    else:
        assert await journal.append_original(
            OriginalTraceScope("chat1", "turn1", ("recent",)), messages[-2:]
        )
        scope = replace(scope, segment_ids=(*scope.segment_ids, "recent"))

    async def summarize(trace, _config, _publisher):
        return trace

    monkeypatch.setattr(compaction, "_summarize", summarize)
    result = await compaction.compact_in_turn(
        messages,
        config=make_config(),
        threshold_chars=1_000,
        original_source=journal,
        original_scope=scope,
    )
    assert "özgün iz kullanılamadı" in result[2].content
    assert "kaynak: maskelenmiş özgün segment" not in result[2].content
    assert result[-2:] == messages[-2:]


async def test_reader_ozeti_ozgun_olarak_etiketlerse_compactor_reddeder(monkeypatch):
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))

    class SummaryReader:
        async def read_original(self, requested):
            return OriginalTraceRead(
                requested,
                "redacted_original",
                (Message("user", history.STEPS_SUMMARY_PREFIX + " eski özet", harness_note=True),),
            )

    async def summarize(trace, _config, _publisher):
        return trace

    monkeypatch.setattr(compaction, "_summarize", summarize)
    result = await compaction.compact_in_turn(
        _steps(30),
        config=make_config(),
        threshold_chars=1_000,
        original_source=SummaryReader(),
        original_scope=scope,
    )
    assert "özgün iz kullanılamadı" in result[2].content
    assert "eski özet" not in result[2].content


async def test_istek_kapsami_var_kaynak_yoksa_acik_fallback_yapar(monkeypatch):
    async def summarize(trace, _config, _publisher):
        return trace

    monkeypatch.setattr(compaction, "_summarize", summarize)
    result = await compaction.compact_in_turn(
        _steps(30),
        config=make_config(),
        threshold_chars=1_000,
        original_scope=OriginalTraceScope("chat1", "turn1", ("s1",)),
    )
    assert "özgün iz kullanılamadı" in result[2].content


@pytest.mark.parametrize("compactions", [1, 3, 5])
@pytest.mark.parametrize("use_original", [False, True])
async def test_sentetik_40_adim_replay_kaynak_provenance_ile_ayrilir(
    tmp_path,
    monkeypatch,
    compactions,
    use_original,
    record_property,
):
    """Sabit çıkarıcı ile journal geri kazanımı; gerçek model kazanımı değildir."""
    import json

    markers = ("PATH:src/important.py", "RULE:uzaga-gonderme", "OPEN:C-open")
    journal = FileTurnJournal(tmp_path / "replay.json", original_owner_id="synthetic")
    messages = [Message("system", "kimlik"), Message("user", "sentetik inceleme")]
    trigger_steps = {(index * 40) // compactions for index in range(1, compactions + 1)}
    observed_sources = []

    async def extract(trace, _config, _publisher):
        observed_sources.append("maskelenmiş özgün segment" in trace)
        return "Sabit sentetik çıkarıcı: " + " ".join(
            marker for marker in markers if marker in trace
        )

    monkeypatch.setattr(compaction, "_summarize", extract)
    for step in range(40):
        call = ToolCall(f"c{step}", "read_file", f'{{"path":"src/{step}.py"}}')
        content = " ".join(markers) if step == 0 else f"sentetik sonuç {step}"
        segment = [
            Message("assistant", "karar " + "x" * 300, tool_calls=(call,)),
            Message("tool", content, tool_call_id=call.id),
        ]
        assert await journal.append_original(
            OriginalTraceScope("synthetic", "turn1", (f"s{step}",)),
            segment,
        )
        # Önceden sıkıştırılmış geçmişi açıkça taklit eden kontrollü kayıp enjeksiyonu.
        visible = list(segment)
        if step == 0:
            visible[1] = replace(visible[1], content="önceki sıkıştırmada kaybolmuş sonuç")
        messages.extend(visible)
        if step + 1 not in trigger_steps:
            continue
        anchor = history.task_anchor_length(messages)
        cut = compaction._summary_cut(messages, anchor)
        last_old = max(
            int(call.id[1:]) for message in messages[anchor:cut] for call in message.tool_calls
        )
        scope = OriginalTraceScope(
            "synthetic", "turn1", tuple(f"s{index}" for index in range(last_old + 1))
        )
        messages = await compaction.compact_in_turn(
            messages,
            config=make_config(),
            threshold_chars=1,
            original_source=journal if use_original else None,
            original_scope=scope if use_original else None,
        )
    text = "\n".join(message.content for message in messages)
    retained = [marker in text for marker in markers]
    assert retained == [use_original] * 3
    assert observed_sources == [use_original] * compactions
    assert messages[-1].tool_call_id == "c39"
    record_property(
        "synthetic_replay",
        json.dumps(
            {
                "steps": 40,
                "compactions": compactions,
                "original": use_original,
                "path": retained[0],
                "rule": retained[1],
                "open_marker": retained[2],
                "chars": history.total_chars(messages),
                "summary_calls": len(observed_sources),
                "provenance": "synthetic-loss-injection-fixed-extractor-no-model",
            }
        ),
    )


@pytest.mark.parametrize(
    "scope",
    [
        OriginalTraceScope("chat1", "../turn", ("s1",)),
        OriginalTraceScope("chat1", "..", ("s1",)),
        OriginalTraceScope("chat1", "turn1", (".",)),
        OriginalTraceScope("chat1", "turn1", ()),
        OriginalTraceScope("chat1", "turn1", ("s1", "s1")),
        OriginalTraceScope("chat1", "turn1", tuple(f"s{index}" for index in range(129))),
        OriginalTraceScope("chat1", "turn1", ("s1",), max_chars=0),
        OriginalTraceScope("chat1", "turn1", ("s1",), max_chars=True),
        OriginalTraceScope("chat1", "turn1", ("s1",), max_chars=60_001),
    ],
)
async def test_gecersiz_kapsam_reader_cagrilmadan_fallback_uretir(monkeypatch, scope):
    class ForbiddenReader:
        async def read_original(self, requested):
            raise AssertionError("Geçersiz kapsamda kaynak okunmamalı")

    async def summarize(trace, _config, _publisher):
        return trace

    monkeypatch.setattr(compaction, "_summarize", summarize)
    result = await compaction.compact_in_turn(
        _steps(30),
        config=make_config(),
        threshold_chars=1_000,
        original_source=ForbiddenReader(),
        original_scope=scope,
    )
    assert "özgün iz kullanılamadı (invalid_scope)" in result[2].content


@pytest.mark.parametrize(
    "malformed", ["before", "wrong_call_role", "cross_group", "interrupted", "wrong_result_role"]
)
async def test_sequence_grammar_rejects_impossible_original_batches(tmp_path, malformed):
    first = ToolCall("c1", "read_file", "{}")
    second = ToolCall("c2", "read_file", "{}")
    request = Message("assistant", "", tool_calls=(first,))
    result = Message("tool", "sonuç", tool_call_id="c1")
    cases = {
        "before": [result, request],
        "wrong_call_role": [Message("user", "", tool_calls=(first,)), result],
        "cross_group": [
            request,
            Message("assistant", "", tool_calls=(second,)),
            Message("tool", "ikinci", tool_call_id="c2"),
            result,
        ],
        "interrupted": [request, Message("user", "araya girdi"), result],
        "wrong_result_role": [request, Message("user", "yanlış sonuç", tool_call_id="c1"), result],
    }
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    assert not OriginalTraceRead(scope, "redacted_original", tuple(cases[malformed])).is_usable()
    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    assert not await journal.append_original(scope, cases[malformed])
    assert not journal.original_path.exists()


async def test_sequence_grammar_accepts_reordered_results_inside_completed_groups(tmp_path):
    calls = (ToolCall("c1", "read_file", "{}"), ToolCall("c2", "read_file", "{}"))
    third = ToolCall("c3", "read_file", "{}")
    messages = (
        Message("user", "başla"),
        Message("assistant", "", tool_calls=calls),
        Message("tool", "ikinci", tool_call_id="c2"),
        Message("tool", "birinci", tool_call_id="c1"),
        Message("assistant", "grup bitti"),
        Message("user", "devam"),
        Message("assistant", "", tool_calls=(third,)),
        Message("tool", "üçüncü", tool_call_id="c3"),
    )
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    assert OriginalTraceRead(scope, "redacted_original", messages).is_usable()
    journal = FileTurnJournal(tmp_path / "j.json", original_owner_id="chat1")
    assert await journal.append_original(scope, messages)
    assert (await journal.read_original(scope)).messages == messages


async def test_compactor_rejects_reader_with_result_before_call(monkeypatch):
    scope = OriginalTraceScope("chat1", "turn1", ("s1",))
    messages = _steps(30)

    class OutOfOrderReader:
        async def read_original(self, requested):
            originals = list(messages[2:42])
            originals[0], originals[1] = originals[1], originals[0]
            return OriginalTraceRead(requested, "redacted_original", tuple(originals))

    async def summarize(trace, _config, _publisher):
        return trace

    monkeypatch.setattr(compaction, "_summarize", summarize)
    result = await compaction.compact_in_turn(
        messages,
        config=make_config(),
        threshold_chars=1_000,
        original_source=OutOfOrderReader(),
        original_scope=scope,
    )
    assert "özgün iz kullanılamadı (incomplete)" in result[2].content
    assert "kaynak: maskelenmiş özgün segment" not in result[2].content

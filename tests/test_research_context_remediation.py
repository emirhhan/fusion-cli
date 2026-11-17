"""Araştırma kaynakları ve uzun ara talimatın sıkıştırma sözleşmesi."""

from __future__ import annotations

from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent import compaction, history, masking


def _sources(count=12):
    messages = [Message("system", "kimlik"), Message("user", "kaynakları karşılaştır")]
    for index in range(count):
        call = ToolCall(str(index), "web_fetch", '{"url":"https://source.test/' + str(index) + '"}')
        messages.extend(
            (
                Message("assistant", "", tool_calls=(call,)),
                Message(
                    "tool",
                    f"Kaynak {index}: tutar={index + 10}\n" + "a" * 600,
                    name="web_fetch",
                    tool_call_id=str(index),
                    ok=True,
                ),
            )
        )
    return messages


def test_twelve_source_synthesis_retains_all_values_and_provenance():
    messages = _sources()
    result = masking.mask_view(messages, 8, masking.MaskLedger())
    visible = "\n".join(message.content for message in result.messages)
    for index in range(12):
        assert f"Kaynak {index}: tutar={index + 10}\n" in visible
    assert (
        sum(
            int(message.content.split("tutar=")[1].splitlines()[0])
            for message in result.messages
            if message.name == "web_fetch"
        )
        == 186
    )
    assert result.messages == messages


async def test_compaction_summarizer_receives_evidence_before_cleanup(monkeypatch):
    seen = []

    async def summarize(trace, *_args, **_kwargs):
        seen.append(trace)
        return "özet"

    monkeypatch.setattr(compaction, "_summarize", summarize)
    messages = _sources(20)
    messages.insert(2, Message("assistant", "karar " * 1000))
    await compaction.compact_in_turn(messages, config=None, threshold_chars=2500)
    assert seen
    assert "Kaynak 0: tutar=10" in seen[0]


async def test_late_user_delivery_condition_survives_successive_compactions(monkeypatch):
    async def summarize(*_args, **_kwargs):
        return "ayrıntısız özet"

    monkeypatch.setattr(compaction, "_summarize", summarize)
    correction = Message("user", "Ara açıklama " * 220 + "\nTeslimde GEREKSINIM_SONDA.csv üret.")
    messages = _sources(20)
    messages.insert(4, correction)
    first = await compaction.compress(messages, config=None, manual=True)
    assert correction in first
    second = await compaction.compress(first + _sources(12)[2:], config=None, manual=True)
    assert correction in second
    assert "GEREKSINIM_SONDA.csv" in history.transcript([correction], message_chars=2000)


def test_source_budget_includes_call_metadata_and_sampling_notices():
    from fusion_cli.engines.agent.research_evidence import (
        RESEARCH_EVIDENCE_CHARS,
        bounded_evidence,
        evidence_metadata_chars,
    )

    messages = _sources(60)
    projection = bounded_evidence(messages)
    assert projection
    assert (
        evidence_metadata_chars(messages) + sum(len(m.content) for m in projection.values())
        <= RESEARCH_EVIDENCE_CHARS
    )
    assert all(message.content for message in projection.values())
    assert all("örneklendi" in message.content for message in projection.values())


async def test_more_source_identities_than_budget_refuses_silent_loss(monkeypatch):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("kimlik bütçesi yetmezken kayıplı özet üretilmemeli")

    monkeypatch.setattr(compaction, "_summarize", forbidden)
    messages = _sources(17000)
    result = await compaction.compact_in_turn(messages, config=None, threshold_chars=1000)
    assert result is messages
    assert all(message.content for message in result if message.role == "tool")


async def test_long_source_urls_are_budgeted_before_compaction(monkeypatch):
    from dataclasses import replace

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("URL kimliği sessiz taslağa çevrilmemeli")

    monkeypatch.setattr(compaction, "_summarize", forbidden)
    messages = _sources()
    for index, message in enumerate(messages):
        if message.tool_calls:
            call = replace(
                message.tool_calls[0], arguments='{"url":"https://source.test/' + "a" * 2000 + '"}'
            )
            messages[index] = replace(message, tool_calls=(call,))
    result = await compaction.compact_in_turn(messages, config=None, threshold_chars=1000)
    assert result is messages


def test_source_url_is_not_replaced_by_generic_argument_stub():
    from dataclasses import replace

    messages = _sources(2)
    call = replace(
        messages[2].tool_calls[0], arguments='{"url":"https://source.test/' + "a" * 600 + '"}'
    )
    messages[2] = replace(messages[2], tool_calls=(call,))
    cleaned = history.clear_old_tool_outputs(messages, threshold_chars=200)
    assert cleaned[2].tool_calls[0].arguments == call.arguments

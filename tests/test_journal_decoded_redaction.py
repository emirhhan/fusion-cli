"""Gerçek özgün iz üreticisi, journal ve okuyucu aynı decoded sır politikasını kullanır."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from fusion_cli.core.types import Message, ToolCall
from fusion_cli.engines.agent.context_projection import OriginalCursor
from fusion_cli.memory.turn_journal import FileTurnJournal


@pytest.mark.parametrize(
    "arguments, expected, canary",
    [
        pytest.param(
            {"passwd": "IN02_CONTROL_PASSWORD", "safe": [1, True, "visible"]},
            {"passwd": "[gizlendi]", "safe": [1, True, "visible"]},
            "IN02_CONTROL_PASSWORD",
            id="legacy_alias_passwd",
        ),
        pytest.param(
            {"api-key": "IN02_CONTROL_API", "safe": [1, True, "visible"]},
            {"api-key": "[gizlendi]", "safe": [1, True, "visible"]},
            "IN02_CONTROL_API",
            id="legacy_alias_api_key",
        ),
        pytest.param(
            {"access-token": "IN02_CONTROL_TOKEN", "safe": [1, True, "visible"]},
            {"access-token": "[gizlendi]", "safe": [1, True, "visible"]},
            "IN02_CONTROL_TOKEN",
            id="legacy_alias_access_token",
        ),
        pytest.param(
            {"password": 982761, "safe": "visible", "count": 3},
            {"password": "[gizlendi]", "safe": "visible", "count": 3},
            "982761",
            id="numeric_password",
        ),
        pytest.param(
            {"credentials": {"value": "IN02_SYNTHETIC_OBJECT"}, "safe": {"count": 2}},
            {"credentials": "[gizlendi]", "safe": {"count": 2}},
            "IN02_SYNTHETIC_OBJECT",
            id="secret_object",
        ),
        pytest.param(
            {"credentials": [{"value": "IN02_SYNTHETIC_LIST"}, 982763], "safe": [1, True]},
            {"credentials": "[gizlendi]", "safe": [1, True]},
            "IN02_SYNTHETIC_LIST",
            id="secret_list",
        ),
        pytest.param(
            {"items": [{"password": 982764, "name": "visible"}], "count": 2},
            {"items": [{"password": "[gizlendi]", "name": "visible"}], "count": 2},
            "982764",
            id="secret_inside_safe_list",
        ),
    ],
)
async def test_cursor_journal_scoped_read_redacts_decoded_secrets(
    tmp_path, arguments, expected, canary
):
    journal = FileTurnJournal(tmp_path / "journal.json", original_owner_id="owner")
    deps = SimpleNamespace(
        config=SimpleNamespace(runtime=SimpleNamespace(context_original_trace=True)),
        journal=journal,
        attempt_id="turn",
    )
    cursor = OriginalCursor()
    call = ToolCall("call1", "fixture_tool", json.dumps(arguments))
    messages = [
        Message("assistant", "", tool_calls=(call,)),
        Message("tool", "ok", tool_call_id=call.id),
    ]

    await cursor.append(messages, deps)

    serialized = journal.original_path.read_text()
    persisted = json.loads(serialized)
    decoded = json.loads(persisted["mesajlar"][0]["araclar"][0]["arguman"])
    assert decoded == expected
    assert canary not in serialized
    scope = cursor.scope(messages, [], deps)
    assert scope is not None
    restored = await journal.read_original(scope)
    assert restored.status == "redacted_original" and restored.is_usable()
    assert json.loads(restored.messages[0].tool_calls[0].arguments) == expected
    assert canary not in restored.messages[0].tool_calls[0].arguments
    journal.save(messages)
    snapshot = journal.load()
    assert snapshot is not None
    assert json.loads(snapshot.messages[0].tool_calls[0].arguments) == expected
    assert canary not in journal.path.read_text()


async def test_cursor_journal_invalid_json_keeps_redacted_plaintext_fallback(tmp_path):
    journal = FileTurnJournal(tmp_path / "journal.json", original_owner_id="owner")
    deps = SimpleNamespace(
        config=SimpleNamespace(runtime=SimpleNamespace(context_original_trace=True)),
        journal=journal,
        attempt_id="turn",
    )
    cursor = OriginalCursor()
    call = ToolCall("call1", "fixture_tool", "password=IN02_SYNTHETIC_TEXT path=visible {")
    messages = [
        Message("assistant", "", tool_calls=(call,)),
        Message("tool", "ok", tool_call_id=call.id),
    ]

    await cursor.append(messages, deps)

    scope = cursor.scope(messages, [], deps)
    assert scope is not None
    restored = await journal.read_original(scope)
    assert restored.is_usable()
    assert restored.messages[0].tool_calls[0].arguments == "[gizlendi] path=visible {"
    assert "IN02_SYNTHETIC_TEXT" not in journal.original_path.read_text()


async def test_cursor_keeps_original_journal_disabled_when_flag_is_false(tmp_path):
    journal = FileTurnJournal(tmp_path / "journal.json", original_owner_id="owner")
    deps = SimpleNamespace(
        config=SimpleNamespace(runtime=SimpleNamespace(context_original_trace=False)),
        journal=journal,
        attempt_id="turn",
    )
    cursor = OriginalCursor()
    call = ToolCall("call1", "fixture_tool", '{"password":982761}')
    await cursor.append(
        [Message("assistant", "", tool_calls=(call,)), Message("tool", "ok", tool_call_id=call.id)],
        deps,
    )
    assert not journal.original_path.exists()
    assert cursor.segments == []

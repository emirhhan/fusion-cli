import base64

from fusion_cli.appserver.session import _attachment_context, _attachment_images
from fusion_cli.cli.repl.transcript_store import TranscriptStore, load_transcript_messages
from fusion_cli.core.types import Message
from fusion_cli.memory.turn_journal import FileTurnJournal

PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_image_budget_is_independent_of_text_attachments(tmp_path):
    text = tmp_path / "a.txt"
    text.write_text("hello")
    image = tmp_path / "a.png"
    image.write_bytes(base64.b64decode(PNG))
    items = [{"path": str(text), "kind": "file"} for _ in range(8)]
    items.append({"path": str(image), "kind": "image"})
    assert len(_attachment_images(items)) == 1


def test_attachment_overflow_is_explicit(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("hello")
    _, error = _attachment_context([{"path": str(path)}] * 21)
    assert error and "20" in error


def test_reload_preserves_bounded_original_requirement(tmp_path):
    store = TranscriptStore(tmp_path / "memory", tmp_path, conversation_id="conversation")
    store.record_user("ROOT_REQUIREMENT")
    store.record_assistant("first answer")
    for i in range(50):
        store.record_user(f"followup {i}")
        store.record_assistant(f"answer {i}")
    messages = load_transcript_messages(
        tmp_path / "memory", tmp_path, conversation_id="conversation"
    )
    assert len(messages) <= 100
    assert sum("ROOT_REQUIREMENT" in m.content for m in messages) == 1
    assert messages[-1].content == "answer 49"
    assert any(m.harness_note for m in messages)


def test_journal_preserves_valid_image(tmp_path):
    image = "data:image/png;base64," + PNG
    journal = FileTurnJournal(tmp_path / "journal.json")
    journal.save([Message("user", "inspect", images=(image,))])
    assert journal.load().messages[0].images == (image,)
    assert (tmp_path / "journal.json").stat().st_mode & 0o777 == 0o600


async def test_compact_discovery_and_loaded_tool_survive_budget():
    from fusion_cli.engines.agent.tool_surface import narrow_to_compact_surface
    from fusion_cli.tools.tool_search import TOOL_SEARCH, ToolSearchMode, visible_tool_names
    from tests.test_mcp_tool_search import _ara, _Arac, _defter

    registry = await _defter(ToolSearchMode(True), *[_Arac(f"tool_{i}") for i in range(13)])

    def compact():
        return narrow_to_compact_surface(
            set(registry.names()), registry, max_external_tools=12, task_kinds=(), explicit=None
        )

    assert TOOL_SEARCH in compact()
    await _ara(registry, {"query": "select:mcp__gh__tool_12"})
    names = compact()
    assert "mcp__gh__tool_12" in visible_tool_names(names, registry, lambda: 200000)
    assert len(names - {TOOL_SEARCH}) <= 12


def test_invalid_and_oversized_image_recovery_is_explicit(tmp_path):
    from fusion_cli.core.image_input import MAX_IMAGE_BYTES, valid_image_uri

    assert not valid_image_uri("data:image/png;base64,@@@")
    assert not valid_image_uri("https://example.test/private.png?token=secret")
    assert not valid_image_uri("data:image/png;base64," + "A" * (MAX_IMAGE_BYTES * 2))
    journal = FileTurnJournal(tmp_path / "journal.json")
    journal.save([Message("user", "inspect", images=("data:image/png;base64,@@@",))])
    restored = journal.load().messages[0]
    assert not restored.images
    assert "yeniden ekleyin" in restored.content
    assert "@@@" not in (tmp_path / "journal.json").read_text()


async def test_latest_tool_search_selection_replaces_old_slots():
    from fusion_cli.engines.agent.tool_surface import narrow_to_compact_surface
    from fusion_cli.tools.tool_search import TOOL_SEARCH, ToolSearchMode
    from tests.test_mcp_tool_search import _ara, _Arac, _defter

    registry = await _defter(ToolSearchMode(True), *[_Arac(f"tool_{i}") for i in range(14)])
    await _ara(
        registry,
        {"query": "select:" + ",".join(f"mcp__gh__tool_{i}" for i in range(12)), "max_results": 12},
    )
    await _ara(registry, {"query": "select:mcp__gh__tool_13"})
    names = narrow_to_compact_surface(
        set(registry.names()), registry, max_external_tools=12, task_kinds=(), explicit=None
    )
    assert "mcp__gh__tool_13" in names
    assert len(names - {TOOL_SEARCH}) == 12


async def test_search_result_limit_matches_smaller_surface_budget():
    from fusion_cli.engines.agent.tool_surface import narrow_to_compact_surface
    from fusion_cli.tools.tool_search import ToolSearchMode
    from tests.test_mcp_tool_search import _ara, _Arac, _defter

    registry = await _defter(ToolSearchMode(True), _Arac("a"), _Arac("b"))
    narrow_to_compact_surface(
        set(registry.names()), registry, max_external_tools=1, task_kinds=(), explicit=None
    )
    result = await _ara(registry, {"query": "select:mcp__gh__a,mcp__gh__b", "max_results": 12})
    assert result.output.count("<function>") == 1


def test_corrupt_png_checksum_is_rejected_without_breaking_journal(tmp_path):
    from fusion_cli.core.image_input import valid_image_uri

    raw = bytearray(base64.b64decode(PNG))
    raw[45] ^= 1
    image = "data:image/png;base64," + base64.b64encode(raw).decode()
    assert not valid_image_uri(image)
    journal = FileTurnJournal(tmp_path / "journal.json")
    journal.save([Message("user", "inspect", images=(image,))])
    assert "yeniden ekleyin" in journal.load().messages[0].content


def test_attachment_home_expansion_error_is_bounded(monkeypatch):
    from pathlib import Path

    def unavailable_home(_path):
        raise RuntimeError("HOME_LOOKUP_PRIVATE_DETAIL")

    monkeypatch.setattr(Path, "expanduser", unavailable_home)
    context, error = _attachment_context([{"path": "~unknown/image.png", "kind": "image"}])
    assert not context
    assert error and len(error) < 200
    assert "HOME_LOOKUP_PRIVATE_DETAIL" not in error


def test_disappeared_admitted_image_fails_visibly(tmp_path):
    import pytest

    image = tmp_path / "vanished.png"
    image.write_bytes(base64.b64decode(PNG))
    items = [{"path": str(image), "kind": "image"}]
    assert _attachment_context(items)[1] is None
    image.unlink()
    with pytest.raises(ValueError, match="Ek açılamadı"):
        _attachment_images(items)


def test_branch_preserves_reload_requirement_without_other_harness_notes(tmp_path):
    from fusion_cli.cli.repl.transcript_store import copy_conversation

    memory = tmp_path / "memory"
    store = TranscriptStore(memory, tmp_path, conversation_id="original")
    store.record_user("ROOT_REQUIREMENT")
    for i in range(101):
        if i == 100:
            store.record_user("continue")
        store.record_assistant(f"answer {i}")
    messages = load_transcript_messages(memory, tmp_path, conversation_id="original")
    messages.append(Message("user", "INTERNAL_NOTE_DO_NOT_COPY", harness_note=True))
    copy_conversation(memory, tmp_path, messages, target_id="branch")
    branch = load_transcript_messages(memory, tmp_path, conversation_id="branch")
    assert len(branch) <= 100
    assert sum("ROOT_REQUIREMENT" in message.content for message in branch) == 1
    assert not any("INTERNAL_NOTE_DO_NOT_COPY" in message.content for message in branch)
    copy_conversation(memory, tmp_path, branch, target_id="branch-again")
    again = load_transcript_messages(memory, tmp_path, conversation_id="branch-again")
    assert sum("ROOT_REQUIREMENT" in message.content for message in again) == 1
    assert again[-1].content == "answer 100"


async def test_session_rejects_image_deleted_after_metadata_admission(tmp_path, monkeypatch):
    from fusion_cli.appserver import session as session_module
    from fusion_cli.appserver.protocol import Request
    from tests.test_appserver_session import _session, _sonuc

    image = tmp_path / "vanished.png"
    image.write_bytes(base64.b64decode(PNG))
    original = session_module._attachment_context

    def admitted_then_deleted(value):
        result = original(value)
        assert result[1] is None
        image.unlink()
        return result

    def must_not_run(*_args, **_kwargs):
        raise AssertionError("The agent must not run without the admitted image")

    monkeypatch.setattr(session_module, "_attachment_context", admitted_then_deleted)
    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", must_not_run)
    lines = []
    session = _session(tmp_path, lines)
    await session.handle(
        Request(
            id="race",
            name="tur.calistir",
            data={
                "gorev": "inspect image",
                "ekler": [{"path": str(image), "kind": "image"}],
            },
        )
    )
    result = _sonuc(lines, "race")
    assert result["ok"] is False
    assert "vanished.png" in result["metin"]


def test_requirement_only_branch_is_listed_and_not_counted_as_rewind_user(tmp_path):
    from fusion_cli.cli.repl.transcript_store import copy_conversation, list_conversations

    memory = tmp_path / "memory"
    original = TranscriptStore(memory, tmp_path, conversation_id="original")
    original.record_user("ROOT_REQUIREMENT")
    for i in range(101):
        original.record_assistant(f"answer {i}")
    messages = load_transcript_messages(memory, tmp_path, conversation_id="original")
    copy_conversation(memory, tmp_path, messages, target_id="branch")
    assert any(ref.conversation_id == "branch" for ref in list_conversations(memory, tmp_path))
    branch = TranscriptStore(memory, tmp_path, conversation_id="branch")
    branch.record_user("discard this user")
    branch.record_assistant("discard this answer")
    branch.record_rewind(0)
    restored = load_transcript_messages(memory, tmp_path, conversation_id="branch")
    assert sum("ROOT_REQUIREMENT" in m.content for m in restored) == 1
    assert not any("discard this" in m.content for m in restored)
    assert restored[-1].content == "answer 100"

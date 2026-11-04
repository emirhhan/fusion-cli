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

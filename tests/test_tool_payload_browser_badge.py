from __future__ import annotations

import json

from fusion_cli.core.tool_emulation import (
    PAYLOAD_SENTINEL,
    parse_tool_calls,
    render_tool_instructions,
)
from fusion_cli.engines.agent.reflexion import tool_contract_repair_note
from fusion_cli.tools import build_registry


def _call(path: str = "example.py") -> str:
    payload = {
        "name": "write_file",
        "arguments": {
            "path": path,
            "content": {"$ref": "source-1"},
        },
    }
    return f"<tool_call>{json.dumps(payload)}</tool_call>"


def test_raw_fenced_sentinel_payload_preserves_exact_python() -> None:
    source = (
        "import re\n\n"
        "def normalize(text: str) -> str:\n"
        "    if not text:\n"
        '        return ""\n'
        "    return re.sub(r'\\s+', ' ', text).strip()\n\n"
        'if __name__ == "__main__":\n'
        '    print(normalize("  ok  "))'
    )
    raw = (
        f'<tool_payload id="source-1" lines="{len(source.splitlines())}">\n'
        "```python\n"
        f"{PAYLOAD_SENTINEL}\n"
        f"{source}\n"
        "```\n"
        "</tool_payload>\n"
        f"{_call()}"
    )

    parsed = parse_tool_calls(raw)

    assert not parsed.errors
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments["content"] == source


def test_browser_language_badge_before_sentinel_is_removed() -> None:
    source = (
        'import re\n\ndef normalize_spaces(text: str) -> str:\n    return " ".join(text.split())'
    )
    browser_rendered = (
        f'<tool_payload id="source-1" lines="{len(source.splitlines())}">\n'
        "Python\n"
        f"{PAYLOAD_SENTINEL}\n"
        f"{source}\n"
        "</tool_payload>\n"
        f"{_call()}"
    )

    parsed = parse_tool_calls(browser_rendered)

    assert not parsed.errors
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments["content"] == source


def test_multiple_toolbar_lines_before_sentinel_are_removed() -> None:
    source = 'print("ok")'
    browser_rendered = (
        f'<tool_payload id="source-1" lines="{len(source.splitlines())}">\n'
        "Python\n"
        "Copy code\n"
        f"{PAYLOAD_SENTINEL}\n"
        f"{source}\n"
        "</tool_payload>\n"
        f"{_call()}"
    )

    parsed = parse_tool_calls(browser_rendered)

    assert not parsed.errors
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments["content"] == source


def test_legacy_payload_without_sentinel_remains_unchanged() -> None:
    source = "Python\nBu gerçek dosya içeriğidir."
    raw = (
        f'<tool_payload id="source-1" lines="{len(source.splitlines())}">\n'
        f"{source}\n"
        "</tool_payload>\n"
        f"{_call('notes.txt')}"
    )

    parsed = parse_tool_calls(raw)

    assert not parsed.errors
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments["content"] == source


def test_old_python_badge_output_has_conservative_recovery() -> None:
    source = "import unittest\n\nclass Example(unittest.TestCase):\n    pass"
    raw = (
        f'<tool_payload id="source-1" lines="{len(source.splitlines())}">\n'
        "Python\n"
        f"{source}\n"
        "</tool_payload>\n"
        f"{_call('test_example.py')}"
    )

    parsed = parse_tool_calls(raw)

    assert not parsed.errors
    arguments = json.loads(parsed.calls[0].arguments)
    assert arguments["content"] == source


def test_instructions_and_repair_note_include_sentinel() -> None:
    instructions = render_tool_instructions(build_registry().schemas())
    repair = tool_contract_repair_note("invalid payload")

    assert PAYLOAD_SENTINEL in instructions
    assert PAYLOAD_SENTINEL in repair.content

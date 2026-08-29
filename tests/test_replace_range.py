from __future__ import annotations

import json

from fusion_cli.core.tool_emulation import (
    RANGE_EDIT_EXAMPLE,
    parse_tool_calls,
)
from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import build_registry
from fusion_cli.tools.files import read_file, replace_range
from fusion_cli.tools.preview import preview_change


def test_replace_range_okumadan_duzenlemeyi_reddeder(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    result = replace_range(
        {
            "path": "app.py",
            "start_line": 2,
            "end_line": 2,
            "new": "b = 20",
        },
        context,
    )

    assert not result.ok
    assert "Önce read_file" in result.output
    assert path.read_text(encoding="utf-8") == "a = 1\nb = 2\nc = 3\n"


def test_replace_range_old_payload_olmadan_duzenler(tmp_path):
    path = tmp_path / "app.py"
    path.write_text(
        "def f():\n    x = 1\n    y = 2\n    return x + y\n\nprint(f())\n",
        encoding="utf-8",
    )
    context = ToolContext(root=tmp_path)

    assert read_file({"path": "app.py"}, context).ok

    result = replace_range(
        {
            "path": "app.py",
            "start_line": 2,
            "end_line": 3,
            "new": "    x = 10\n    y = 20",
        },
        context,
    )

    assert result.ok, result.output
    assert path.read_text(encoding="utf-8") == (
        "def f():\n    x = 10\n    y = 20\n    return x + y\n\nprint(f())\n"
    )


def test_replace_range_stale_revisioni_reddeder(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("a = 1\nb = 2\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    assert read_file({"path": "app.py"}, context).ok

    # Modelin görmediği harici değişiklik.
    path.write_text("a = 999\nb = 2\n", encoding="utf-8")

    result = replace_range(
        {
            "path": "app.py",
            "start_line": 2,
            "end_line": 2,
            "new": "b = 20",
        },
        context,
    )

    assert not result.ok
    assert "okunduktan sonra değişmiş" in result.output
    assert path.read_text(encoding="utf-8") == "a = 999\nb = 2\n"


def test_replace_range_sonrasi_yeniden_okuma_ister(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    assert read_file({"path": "app.py"}, context).ok

    first = replace_range(
        {
            "path": "app.py",
            "start_line": 2,
            "end_line": 2,
            "new": "b = 20",
        },
        context,
    )

    assert first.ok

    second = replace_range(
        {
            "path": "app.py",
            "start_line": 3,
            "end_line": 3,
            "new": "c = 30",
        },
        context,
    )

    assert not second.ok
    assert "bu turda okunmadı" in second.output


def test_replace_range_gecersiz_satir_numarasini_reddeder(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("a = 1\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    assert read_file({"path": "app.py"}, context).ok

    result = replace_range(
        {
            "path": "app.py",
            "start_line": 0,
            "end_line": 0,
            "new": "a = 2",
        },
        context,
    )

    assert not result.ok
    assert "pozitif tamsayı" in result.output


def test_replace_range_registryde_mutating_olarak_sunulur():
    tool = build_registry().get("replace_range")

    assert tool is not None
    assert tool.mutating is True

    function = tool.schema()["function"]

    assert function["name"] == "replace_range"
    assert function["parameters"]["required"] == [
        "path",
        "start_line",
        "end_line",
        "new",
    ]


def test_replace_range_preview_gercek_diff_uretir(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
    context = ToolContext(root=tmp_path)

    diff = preview_change(
        "replace_range",
        {
            "path": "app.py",
            "start_line": 2,
            "end_line": 2,
            "new": "b = 20",
        },
        context,
    )

    assert diff is not None
    assert "-b = 2" in diff
    assert "+b = 20" in diff


def test_range_edit_example_kendi_parserimizdan_gecer():
    parsed = parse_tool_calls(RANGE_EDIT_EXAMPLE)

    assert not parsed.errors, parsed.errors
    assert len(parsed.calls) == 1
    assert parsed.calls[0].name == "replace_range"

    arguments = json.loads(parsed.calls[0].arguments)

    assert arguments["path"] == "hesap.py"
    assert arguments["start_line"] == 10
    assert arguments["end_line"] == 11
    assert arguments["new"] == "def topla(a, b):\n    return a + b"

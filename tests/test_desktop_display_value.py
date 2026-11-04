"""Safe display extraction runs pure Swift helpers, never a live desktop probe."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop_background, native_desktop


async def test_native_display_helper_excludes_secure_unknown_and_editable_values(tmp_path):
    swift = shutil.which("swift")
    if swift is None or sys.platform != "darwin":
        pytest.skip("Swift runtime is not available.")
    source = Path(__file__).parents[1] / "src/fusion_cli/tools/data/desktop_host.swift"
    content = source.read_text()
    assert "func displayBranchIsSafe(" in content
    start = content.index("func displayBranchIsSafe(")
    end = content.index("\nfunc tree(", start)
    program = (
        "import Foundation\n"
        + content[start:end]
        + """
precondition(displayBranchIsSafe("AXWindow", "AXStandardWindow", true, nil))
precondition(!displayBranchIsSafe(nil, "", true, nil))
precondition(!displayBranchIsSafe("AXGroup", nil, true, nil))
precondition(!displayBranchIsSafe("AXUnknown", "", true, nil))
precondition(!displayBranchIsSafe("AXStaticText", "", true, nil))
precondition(!displayBranchIsSafe("AXTextField", "", true, true))
precondition(!displayBranchIsSafe("AXGroup", "AXSecureTextField", true, nil))
precondition(!displayBranchIsSafe("AXSecureTextField", "", true, nil))
let secureAncestor = displayBranchIsSafe("AXGroup", "AXSecureTextField", true, nil)
precondition(!displayBranchIsSafe("AXGroup", "", secureAncestor, nil))
precondition(safeDisplayValue("AXStaticText", true, false, "391") == "391")
precondition(safeDisplayValue("AXStaticText", false, false, "password") == nil)
precondition(safeDisplayValue("AXTextField", true, false, "input") == nil)
precondition(safeDisplayValue("AXStaticText", true, true, "input") == nil)
precondition(safeDisplayValue("AXStaticText", true, nil, "unknown") == nil)
precondition(safeDisplayValue(nil, true, false, "unknown") == nil)
precondition(safeDisplayValue("AXStaticText", true, false, nil) == nil)
let longValue = String(repeating: "x", count: 1200)
precondition(safeDisplayValue("AXStaticText", true, false, longValue)?.count == 1000)
print("safe-display-values-passed")
"""
    )
    target = tmp_path / "display.swift"
    target.write_text(program)
    result = await asyncio.to_thread(
        subprocess.run,
        [swift, str(target)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "safe-display-values-passed"


async def test_background_inspect_preserves_literal_native_display_value(tmp_path, monkeypatch):
    invoke = AsyncMock(
        return_value={
            "ok": True,
            "id": 101,
            "pid": 42,
            "elements": [{"role": "AXStaticText", "title": "Display", "value": "17×23−"}],
        }
    )
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_inspect(
        {"window_id": 101, "pid": 42}, ToolContext(tmp_path)
    )
    assert result.ok
    payload = json.loads(result.output)
    assert payload["elements"][0]["value"] == "17×23−"
    assert "391" not in result.output

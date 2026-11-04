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
    assert "enum DisplayEditability" in content
    start = content.index("enum DisplayEditability")
    end = content.index("\nfunc tree(", start)
    program = (
        "import Foundation\nimport ApplicationServices\n"
        + content[start:end]
        + """
precondition(displayEditability(.success, false) == .readOnly)
precondition(displayEditability(.success, true) == .editable)
precondition(displayEditability(.attributeUnsupported, false) == .unsupported)
precondition(displayEditability(.noValue, false) == .unsupported)
for status in [AXError.failure, .cannotComplete, .invalidUIElement, .apiDisabled, .notImplemented] {
    let classification = displayEditability(status, false)
    precondition(classification == .unknown)
    let unsafeParent = displayBranchIsSafe("AXGroup", "", true, classification)
    precondition(!unsafeParent)
    let child = displayBranchIsSafe("AXStaticText", "", unsafeParent, .readOnly)
    precondition(safeDisplayValue("AXStaticText", child, .readOnly, "private") == nil)
}
let window = displayBranchIsSafe("AXWindow", "AXStandardWindow", true,
    displayEditability(.attributeUnsupported, false))
precondition(window)
let group = displayBranchIsSafe("AXGroup", "", window, displayEditability(.noValue, false))
precondition(group)
let text = displayBranchIsSafe("AXStaticText", "", group, .readOnly)
precondition(safeDisplayValue("AXStaticText", text, .readOnly, "391") == "391")
precondition(!displayBranchIsSafe(nil, "", true, .readOnly))
precondition(!displayBranchIsSafe("AXGroup", nil, true, .readOnly))
precondition(!displayBranchIsSafe("AXUnknown", "", true, .readOnly))
precondition(!displayBranchIsSafe("AXGroup", "", true, .editable))
precondition(!displayBranchIsSafe("AXTextField", "", true, .readOnly))
precondition(!displayBranchIsSafe("AXGroup", "AXSecureTextField", true, .unsupported))
precondition(!displayBranchIsSafe("AXSecureTextField", "", true, .unsupported))
let secureAncestor = displayBranchIsSafe("AXGroup", "AXSecureTextField", true, .unsupported)
let secureChild = displayBranchIsSafe("AXStaticText", "", secureAncestor, .readOnly)
precondition(safeDisplayValue("AXStaticText", secureChild, .readOnly, "password") == nil)
precondition(safeDisplayValue("AXTextField", true, .readOnly, "input") == nil)
precondition(safeDisplayValue("AXStaticText", true, .editable, "input") == nil)
precondition(safeDisplayValue("AXStaticText", true, .unsupported, "unsupported") == nil)
precondition(safeDisplayValue("AXStaticText", true, .unknown, "unknown") == nil)
precondition(safeDisplayValue(nil, true, .readOnly, "unknown") == nil)
precondition(safeDisplayValue("AXStaticText", true, .readOnly, nil) == nil)
precondition(safeDisplayValue("AXStaticText", true, .readOnly, NSString(string: "391")) == "391")
struct DescriptionOnly: CustomStringConvertible { var description: String { "391" } }
let unexpected: [Any] = [NSNumber(value: 391), NSNumber(value: false),
    NSArray(array: ["391"]), NSDictionary(dictionary: ["value": "391"]),
    NSData(data: Data([51, 57, 49])), DescriptionOnly()]
for value in unexpected {
    precondition(safeDisplayValue("AXStaticText", true, .readOnly, value) == nil)
}
let longValue = String(repeating: "x", count: 1200)
precondition(safeDisplayValue("AXStaticText", true, .readOnly, longValue)?.count == 1000)
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

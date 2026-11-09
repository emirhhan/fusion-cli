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
precondition(fingerprintValueKind(nil) == "absent")
precondition(fingerprintValueKind("text" as CFString) == "string")
precondition(fingerprintValueKind(NSNumber(value: true)) == "boolean")
precondition(fingerprintValueKind(NSNumber(value: 391)) == "number")
precondition(fingerprintValueKind([] as CFArray) == "array")
precondition(fingerprintValueKind(Data([1, 2]) as CFData) == "other")
var point = CGPoint(x: 1, y: 2)
precondition(fingerprintValueKind(AXValueCreate(.cgPoint, &point)) == "ax_value")
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
let labels = safeActionLabels("AXButton", true, .unsupported, ["AXPress"],
    "Tümünü Sil", "AllClear")
precondition(labels["description"] == "Tümünü Sil")
precondition(labels["identifier"] == "AllClear")
precondition(labels["label"] == "Tümünü Sil")
precondition(labels["label_source"] == "AXDescription")
precondition(safeActionLabels("AXButton", false, .readOnly, ["AXPress"], "private", "id").isEmpty)
precondition(safeActionLabels("AXButton", true, .unknown, ["AXPress"], "private", "id").isEmpty)
precondition(safeActionLabels("AXButton", true, .editable, ["AXPress"], "private", "id").isEmpty)
precondition(safeActionLabels("AXTextField", true, .readOnly, ["AXPress"], "private", "id").isEmpty)
precondition(safeActionLabels("AXButton", true, .readOnly, [], "group", "id").isEmpty)
precondition(safeActionLabels("AXButton", true, .readOnly, ["AXPress"],
    NSNumber(value: 391), nil).isEmpty)
let boundedLabels = safeActionLabels("AXButton", true, .readOnly, ["AXPress"],
    String(repeating: "x", count: 400), String(repeating: "y", count: 400))
precondition(boundedLabels["description"]?.count == 256)
precondition(boundedLabels["identifier"]?.count == 256)
let mainMetadata = safeWindowSelectionMetadata(true, "AXWindow", "AXStandardWindow", true, false)
precondition(mainMetadata["is_main"] as? Bool == true)
precondition(mainMetadata["is_focused"] as? Bool == false)
precondition(mainMetadata["subrole"] as? String == "AXStandardWindow")
precondition(safeWindowSelectionMetadata(false, "AXWindow", "AXStandardWindow", true, true).isEmpty)
let unknownMetadata = safeWindowSelectionMetadata(true, "AXWindow", nil, nil, nil)
precondition(unknownMetadata["is_main"] == nil && unknownMetadata["is_focused"] == nil)
precondition(unknownMetadata["subrole"] == nil)
precondition(safeWindowSelectionMetadata(true, "AXWindow", String(repeating: "x", count: 300),
    nil, nil)["subrole"] as? String == String(repeating: "x", count: 128))
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


async def test_native_inspect_preserves_empty_title_button_description_and_identifier(
    tmp_path, monkeypatch
):
    element = {
        "role": "AXButton",
        "title": "",
        "description": "Tümünü Sil",
        "identifier": "AllClear",
        "label": "Tümünü Sil",
        "actions": ["AXPress"],
        "ref": "chosen-current-ref",
    }
    invoke = AsyncMock(return_value={"ok": True, "elements": [element]})
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_inspect(
        {"window_id": 101, "pid": 42}, ToolContext(tmp_path)
    )
    assert result.ok
    presented = json.loads(result.output)["elements"][0]
    assert presented["ref"].startswith("dref_")
    assert {key: value for key, value in presented.items() if key != "ref"} == {
        key: value for key, value in element.items() if key != "ref"
    }
    assert element["ref"] == "chosen-current-ref"


async def test_unsupported_press_is_not_retried_with_another_reference(tmp_path, monkeypatch):
    invoke = AsyncMock(return_value={"ok": False, "metin": "Öğe AXPress desteklemiyor."})
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_action(
        {"window_id": 101, "pid": 42, "action": "press", "ref": "chosen-current-ref"},
        ToolContext(tmp_path),
    )
    assert not result.ok and "AXPress" in result.output
    assert invoke.await_count == 1
    assert invoke.await_args.args[1]["request"]["ref"] == "chosen-current-ref"


async def test_action_failure_preserves_only_boolean_guard_diagnostics(tmp_path, monkeypatch):
    checks = {
        "tree_complete": True,
        "fingerprint_matches": False,
        "identity_unique": True,
        "path_identity_matches": True,
    }
    invoke = AsyncMock(
        return_value={
            "ok": False,
            "metin": "Hedef öğe değişti veya kimliği belirsiz.",
            "action_checks": {**checks, "private_title": "private", "raw_value": "secret"},
            "raw_value": "secret",
            "value_kinds": {"string": 4, "other": 2, "private": 1, "array": -1, "number": True},
        }
    )
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_action(
        {"window_id": 101, "pid": 42, "action": "press", "ref": "current"},
        ToolContext(tmp_path),
    )
    assert not result.ok
    assert {key: value for key, value in result.structured.items() if key != "native_failure"} == {
        "ok": False,
        "metin": "Hedef öğe değişti veya kimliği belirsiz.",
        "action_checks": checks,
        "value_kinds": {"string": 4, "other": 2},
    }
    diagnostic = result.structured["native_failure"]
    assert diagnostic["cause"] == "stale_tree"
    assert set(diagnostic) == {"cause", "elapsed_ms", "operation", "pid", "window_id"}
    assert json.loads(result.output) == {
        key: value for key, value in result.structured.items() if key != "native_failure"
    }
    assert "secret" not in result.output and "private" not in result.output
    assert invoke.await_count == 1


async def test_swift_action_guard_diagnostics_preserve_every_rejection(tmp_path):
    swift = shutil.which("swift")
    if swift is None or sys.platform != "darwin":
        pytest.skip("Swift runtime is not available.")
    source = Path(__file__).parents[1] / "src/fusion_cli/tools/data/desktop_host.swift"
    content = source.read_text()
    start = content.index("func actionGuardChecks(")
    end = content.index("\nfunc valueKindCounts(", start)
    program = (
        "import Foundation\n"
        + content[start:end]
        + """
let good = actionGuardChecks(36, true, 1, true)
precondition(good.values.allSatisfy { $0 })
for (count, fingerprint, identities, path, failed) in [
    (500, true, 1, true, "tree_complete"),
    (36, false, 1, true, "fingerprint_matches"),
    (36, true, 0, true, "identity_unique"),
    (36, true, 2, true, "identity_unique"),
    (36, true, 1, false, "path_identity_matches")
] {
    let checks = actionGuardChecks(count, fingerprint, identities, path)
    precondition(checks[failed] == false)
    precondition(!checks.values.allSatisfy { $0 })
}
print("action-checks-passed")
"""
    )
    target = tmp_path / "guard.swift"
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
    assert result.stdout.strip() == "action-checks-passed"
    action = content[content.index("func action(") : content.index("// Eylem hedefi")]
    assert "checks.values.allSatisfy" in action
    assert '"action_checks": checks' in action


async def test_system_calculator_proof_requires_actual_pid_bundle_and_resolved_urls(tmp_path):
    swift = shutil.which("swift")
    if swift is None or sys.platform != "darwin":
        pytest.skip("Swift runtime is not available.")
    source = Path(__file__).parents[1] / "src/fusion_cli/tools/data/desktop_host.swift"
    content = source.read_text()
    start = content.index("func isSystemCalculator(")
    end = content.index("\nfunc appInfo(", start)
    fake = tmp_path / "Calculator.app"
    fake.mkdir()
    link = tmp_path / "linked.app"
    link.symlink_to(fake, target_is_directory=True)
    program = (
        "import Foundation\n"
        + content[start:end]
        + """
let bundle = URL(fileURLWithPath: "/System/Applications/Calculator.app")
let executable = bundle.appendingPathComponent("Contents/MacOS/Calculator")
precondition(isSystemCalculator(1396, "com.apple.calculator", bundle, executable))
precondition(!isSystemCalculator(0, "com.apple.calculator", bundle, executable))
precondition(!isSystemCalculator(-1, "com.apple.calculator", bundle, executable))
precondition(!isSystemCalculator(1396, "other", bundle, executable))
precondition(!isSystemCalculator(1396, nil, bundle, executable))
precondition(!isSystemCalculator(1396, "com.apple.calculator", nil, executable))
precondition(!isSystemCalculator(1396, "com.apple.calculator", bundle, nil))
precondition(!isSystemCalculator(1396, "com.apple.calculator",
    URL(fileURLWithPath: "/Applications/Calculator.app"), executable))
precondition(!isSystemCalculator(1396, "com.apple.calculator", bundle,
    URL(fileURLWithPath: "/tmp/Calculator")))
precondition(!isSystemCalculator(1396, "com.apple.calculator",
    URL(string: "https://example.com/System/Applications/Calculator.app"), executable))
let impersonator = URL(fileURLWithPath: CommandLine.arguments[1])
precondition(!isSystemCalculator(1396, "com.apple.calculator", impersonator,
    impersonator.appendingPathComponent("Contents/MacOS/Calculator")))
print("calculator-proof-passed")
"""
    )
    target = tmp_path / "calculator.swift"
    target.write_text(program)
    result = await asyncio.to_thread(
        subprocess.run,
        [swift, str(target), str(link)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "calculator-proof-passed"
    app_info = content[content.index("func appInfo(") : content.index("// A process can own")]
    assert '"system_calculator": isSystemCalculator(pid, app.bundleIdentifier,' in app_info
    assert "app.bundleURL, app.executableURL" in app_info

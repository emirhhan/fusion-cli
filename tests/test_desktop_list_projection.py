"""Native dock icons remain UI metadata, never agent tool-output text."""

import json
from dataclasses import replace
from unittest.mock import AsyncMock

from fusion_cli.appserver.desktop_dock import DesktopDock
from fusion_cli.core.events import ToolExecuted
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import loop
from fusion_cli.tools import desktop_background, native_desktop
from fusion_cli.tools.builtin import build_registry
from fusion_cli.tools.registry import ToolRegistry
from tests.fakes import ScriptedProvider, model_result, tool_call
from tests.test_agent_lessons import _deps


def _payload():
    return {
        "ok": True,
        "windows": [
            {
                "id": 43268,
                "pid": 1396,
                "app": "Calculator",
                "title": "Hesap Makinesi",
                "kind": "window",
                "visible": True,
                "bounds": [350, 260, 230, 408],
                "is_main": True,
                "is_focused": True,
                "subrole": "AXStandardWindow",
                "icon": "data:image/png;base64," + "X" * 128_000,
            }
        ],
    }


def _without_icons(payload):
    return {
        **payload,
        "windows": [{k: v for k, v in row.items() if k != "icon"} for row in payload["windows"]],
    }


async def test_window_tool_text_projects_out_icons_without_mutating_native_ui_payload(
    tmp_path, monkeypatch
):
    payload = _payload()
    invoke = AsyncMock(return_value=payload)
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", invoke)
    result = await desktop_background.desktop_background_windows({}, ToolContext(tmp_path))
    assert result.ok
    assert json.loads(result.output) == _without_icons(payload)
    assert len(result.output) < 1000
    assert "base64" not in result.output and '"icon"' not in result.output
    assert result.structured is None  # Existing tool contract has no icon-structured channel.
    assert payload["windows"][0]["icon"].endswith("X" * 128_000)
    dock = await DesktopDock(native=native_desktop.SwiftDesktop()).list()
    assert dock["windows"] == payload["windows"]
    assert dock["windows"][0]["icon"] == payload["windows"][0]["icon"]


async def test_projection_preserves_legitimate_text_and_inspect_payloads(tmp_path, monkeypatch):
    text = "data:image/png;base64,user-supplied title text"
    payload = _payload()
    payload["windows"][0]["title"] = text
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", AsyncMock(return_value=payload))
    result = await desktop_background.desktop_background_windows({}, ToolContext(tmp_path))
    assert json.loads(result.output)["windows"][0]["title"] == text
    inspection = {"ok": True, "elements": [{"role": "AXStaticText", "value": text}]}
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", AsyncMock(return_value=inspection))
    result = await desktop_background.desktop_background_inspect(
        {"window_id": 43268, "pid": 1396}, ToolContext(tmp_path)
    )
    assert json.loads(result.output) == inspection


async def test_agent_model_messages_and_tool_events_receive_only_text_projection(
    tmp_path, monkeypatch
):
    payload = _payload()
    monkeypatch.setattr(native_desktop.SwiftDesktop, "invoke", AsyncMock(return_value=payload))
    deps = _deps(tmp_path)
    deps.config = replace(deps.config, desktop=replace(deps.config.desktop, enabled=True))
    deps.tool_context = replace(
        deps.tool_context,
        desktop_settings=replace(deps.tool_context.desktop_settings, enabled=True),
    )
    events = []
    deps.publisher = type("Publisher", (), {"publish": lambda self, event: events.append(event)})()
    registry = ToolRegistry()
    registry.register(next(t for t in build_registry() if t.name == "desktop_background_windows"))
    deps.base_registry = registry
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("desktop_background_windows")]),
            model_result("Pencere kimliği 43268, süreç 1396."),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    await loop.run_agent("Masaüstü pencerelerini listele.", deps, verify=False, self_review=False)
    model_outputs = [
        m.content
        for m in provider.seen_messages[1]
        if m.role == "tool" and m.name == "desktop_background_windows"
    ]
    event_outputs = [
        e.output
        for e in events
        if isinstance(e, ToolExecuted) and e.name == "desktop_background_windows"
    ]
    assert model_outputs and event_outputs
    for output in model_outputs + event_outputs:
        assert json.loads(output) == _without_icons(payload)
        assert len(output) < 1000
        assert "base64" not in output and '"icon"' not in output

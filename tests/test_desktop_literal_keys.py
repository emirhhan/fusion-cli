"""Logical arithmetic keys must not use layout-dependent ANSI punctuation."""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop, desktop_lock


class FakeFunction:
    """ctypes-like function supporting signature assignment without loading macOS APIs."""

    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


class FakeCoreGraphics:
    def __init__(self):
        self.created = []
        self.posted = []
        self.released = []
        self.CGEventCreateKeyboardEvent = FakeFunction(self.create)
        self.CGEventSetFlags = FakeFunction(lambda event, flags: event.update(flags=flags))
        self.CGEventPost = FakeFunction(lambda tap, event: self.posted.append(event.copy()))
        self.CFRelease = FakeFunction(self.released.append)

    def create(self, source, code, is_down):
        event = {"code": code, "down": is_down}
        self.created.append(event)
        return event


@pytest.fixture
def graphics(monkeypatch):
    graphics = FakeCoreGraphics()
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "_framework", lambda: graphics)
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: True)
    monkeypatch.setattr(desktop_lock, "claim", lambda **kwargs: None)
    return graphics


def test_arithmetic_sequence_uses_logical_keypad_under_turkish_layout(graphics, tmp_path):
    result = desktop.desktop_key({"key": "1 7 * 2 3 ="}, ToolContext(root=tmp_path))

    assert result.ok, result.output
    # Turkish Q layout: ANSI key 24 produces '-', while keypad Equals produces '='.
    layout = {18: "1", 26: "7", 0x43: "*", 19: "2", 20: "3", 24: "-", 0x51: "="}
    down = [event for event in graphics.posted if event["down"]]
    assert "".join(layout[event["code"]] for event in down) == "17*23="
    assert [event["code"] for event in down] == [18, 26, 0x43, 19, 20, 0x51]
    assert all(event["flags"] == 0 for event in graphics.posted)
    assert [event["down"] for event in graphics.posted] == [True, False] * 6
    assert graphics.released == graphics.created


@pytest.mark.parametrize(("key", "code"), [("+", 0x45), ("-", 0x4E), ("/", 0x4B)])
def test_unmodified_arithmetic_uses_keypad(graphics, tmp_path, key, code):
    assert desktop.desktop_key({"key": key}, ToolContext(root=tmp_path)).ok
    assert [event["code"] for event in graphics.posted] == [code, code]
    assert all(event["flags"] == 0 for event in graphics.posted)


@pytest.mark.parametrize("key", ["=", "+", "-", "/", "*"])
@pytest.mark.parametrize("modifier", ["command", "control", "option", "shift"])
def test_modified_arithmetic_preserves_shortcut_keycodes(graphics, tmp_path, key, modifier):
    assert desktop.desktop_key({"key": key, modifier: True}, ToolContext(root=tmp_path)).ok
    assert [event["code"] for event in graphics.posted] == [desktop.KEY_CODES[key]] * 2
    assert all(
        event["flags"] == desktop.modifier_flags(**{modifier: True}) for event in graphics.posted
    )


def test_named_navigation_and_repeat_hold_are_preserved(graphics, tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr(desktop.time, "sleep", sleeps.append)
    assert desktop.desktop_key(
        {"key": "= enter left", "repeat": 2, "hold_ms": 20}, ToolContext(root=tmp_path)
    ).ok
    assert [event["code"] for event in graphics.posted] == [0x51, 0x51, 36, 36, 123, 123] * 2
    assert sleeps == [0.02] * 6

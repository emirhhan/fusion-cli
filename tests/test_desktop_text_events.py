"""Text dispatch must work for consumers that handle one character per key event.

These tests capture production CG event dispatch without calling native APIs.
Actual Calculator compatibility still requires a native acceptance test.
"""

from __future__ import annotations

from threading import Event

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import desktop


class _Function:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


class _Graphics:
    def __init__(self, *, fail=None, cancel_on_down=None):
        self.fail = fail
        self.cancel_on_down = cancel_on_down
        self.created = []
        self.posted = []
        self.attempted = []
        self.released = []
        self.unicode_calls = 0
        self.create_calls = 0
        self.CGEventCreateKeyboardEvent = _Function(self.create)
        self.CGEventKeyboardSetUnicodeString = _Function(self.unicode)
        self.CGEventPost = _Function(self.post)
        self.CFRelease = _Function(self.released.append)

    def create(self, source, code, is_down):
        self.create_calls += 1
        if self.fail == ("create", self.create_calls):
            return None
        event = {"code": code, "down": is_down}
        self.created.append(event)
        return event

    def unicode(self, event, count, pointer):
        self.unicode_calls += 1
        if self.fail == ("unicode", self.unicode_calls):
            raise RuntimeError("synthetic Unicode assignment failure")
        units = list(pointer[:count])
        event["units"] = units
        event["text"] = b"".join(unit.to_bytes(2, "little") for unit in units).decode("utf-16-le")

    def post(self, tap, event):
        self.attempted.append(event.copy())
        if self.fail == ("post", len(self.attempted)):
            raise RuntimeError("synthetic event post failure")
        self.posted.append(event.copy())
        if event["down"] and self.cancel_on_down is not None:
            self.cancel_on_down.set()


def _assert_released(graphics):
    assert [id(event) for event in graphics.released] == [id(event) for event in graphics.created]


@pytest.mark.parametrize("value", ["18*24", "ö😀e\u0301", "line 1\nline 2", ""])
def test_each_unicode_scalar_gets_its_own_complete_key_pair(value):
    graphics = _Graphics()

    desktop._post_text(graphics, value)

    down = [event for event in graphics.posted if event["down"]]
    assert [event["text"] for event in down] == list(value)
    assert [event["down"] for event in graphics.posted] == [True, False] * len(value)
    assert [event["text"] for event in graphics.posted] == [
        char for char in value for _ in range(2)
    ]
    _assert_released(graphics)


def test_astral_scalar_keeps_its_surrogate_pair_in_one_event():
    graphics = _Graphics()

    desktop._post_text(graphics, "😀")

    assert [event["units"] for event in graphics.posted] == [[0xD83D, 0xDE00]] * 2


def test_invalid_unicode_is_rejected_before_any_event_is_created():
    graphics = _Graphics()

    with pytest.raises(UnicodeError):
        desktop._post_text(graphics, "valid prefix\ud800")

    assert graphics.created == graphics.posted == []


def test_cancellation_before_dispatch_posts_nothing():
    graphics = _Graphics()
    cancelled = Event()
    cancelled.set()

    assert desktop._post_text(graphics, "secret", cancelled=cancelled) == 0

    assert graphics.created == graphics.posted == []


def test_cancellation_after_keydown_finishes_keyup_and_stops_before_next_character():
    cancelled = Event()
    graphics = _Graphics(cancel_on_down=cancelled)

    assert desktop._post_text(graphics, "secret", cancelled=cancelled) == 1

    assert [event["down"] for event in graphics.posted] == [True, False]
    assert [event["text"] for event in graphics.posted] == ["s", "s"]
    _assert_released(graphics)


def test_cancellation_while_preparing_events_releases_without_dispatching():
    cancelled = Event()
    graphics = _Graphics()

    def unicode_and_cancel(*args):
        graphics.unicode(*args)
        cancelled.set()

    graphics.CGEventKeyboardSetUnicodeString = _Function(unicode_and_cancel)

    assert desktop._post_text(graphics, "secret", cancelled=cancelled) == 0

    assert graphics.posted == []
    assert len(graphics.created) == 2
    _assert_released(graphics)


@pytest.mark.parametrize("stage", ["create", "unicode"])
@pytest.mark.parametrize("index", [1, 2])
def test_prepare_failure_posts_no_partial_key_and_releases_allocated_events(stage, index):
    graphics = _Graphics(fail=(stage, index))

    with pytest.raises(RuntimeError):
        desktop._post_text(graphics, "ab")

    assert graphics.posted == []
    _assert_released(graphics)


@pytest.mark.parametrize("index", [1, 2])
def test_post_failure_still_attempts_keyup_and_releases_both_events(index):
    graphics = _Graphics(fail=("post", index))

    with pytest.raises(RuntimeError):
        desktop._post_text(graphics, "ab")

    assert [event["down"] for event in graphics.attempted] == [True, False]
    _assert_released(graphics)


@pytest.fixture
def graphics(monkeypatch):
    graphics = _Graphics()
    monkeypatch.setattr(desktop, "_supported", lambda: None)
    monkeypatch.setattr(desktop.desktop_win32, "active", lambda: False)
    monkeypatch.setattr(desktop, "_framework", lambda: graphics)
    monkeypatch.setattr(desktop, "_trusted", lambda loaded: True)
    monkeypatch.setattr(desktop.desktop_turn, "claim_lock", lambda context: None)
    monkeypatch.setattr(desktop.desktop_turn, "foreground_action", lambda context: None)
    return graphics


def test_type_cancellation_reports_partial_dispatch_without_claiming_insertion(graphics, tmp_path):
    context = ToolContext(root=tmp_path)
    graphics.cancel_on_down = context.cancelled

    result = desktop.desktop_type({"text": "secret"}, context)

    assert not result.ok
    assert "1/6" in result.output
    assert "secret" not in result.output
    assert "yazıldı" not in result.output
    assert len(graphics.posted) == 2


def test_type_reports_dispatch_not_target_content(graphics, tmp_path):
    result = desktop.desktop_type({"text": "secret"}, ToolContext(root=tmp_path))

    assert result.ok
    assert "6" in result.output
    assert "gönderildi" in result.output
    assert "secret" not in result.output
    assert "yazıldı" not in result.output


def test_type_invalid_unicode_returns_failure_without_dispatch_or_content(graphics, tmp_path):
    result = desktop.desktop_type({"text": "secret\ud800"}, ToolContext(root=tmp_path))

    assert not result.ok
    assert "secret" not in result.output
    assert graphics.created == graphics.posted == []


def test_original_text_limit_is_preserved(graphics, tmp_path):
    result = desktop.desktop_type(
        {"text": "a" * desktop.DESKTOP_TEXT_MAX_CHARS}, ToolContext(root=tmp_path)
    )

    assert result.ok
    assert len(graphics.posted) == 2 * desktop.DESKTOP_TEXT_MAX_CHARS
    _assert_released(graphics)


def test_over_limit_text_is_rejected_before_dispatch(graphics, tmp_path):
    result = desktop.desktop_type(
        {"text": "a" * (desktop.DESKTOP_TEXT_MAX_CHARS + 1)}, ToolContext(root=tmp_path)
    )

    assert not result.ok
    assert graphics.created == graphics.posted == []

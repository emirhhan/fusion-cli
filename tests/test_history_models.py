"""Geçmiş kaynaklarının ortak veri modeli."""

from __future__ import annotations

import pytest

from fusion_cli.history.models import SessionRef, Turn


def test_session_ref_carries_fields():
    ref = SessionRef(
        source="claude",
        session_id="abc",
        title="Başlık",
        updated_at=1_700_000_000.0,
        turn_count=12,
    )

    assert ref.source == "claude"
    assert ref.turn_count == 12


def test_session_ref_is_immutable():
    ref = SessionRef(source="claude", session_id="abc", title="B", updated_at=0.0, turn_count=1)

    with pytest.raises(AttributeError):
        ref.title = "yeni"  # type: ignore[misc]


def test_turn_accepts_empty_text():
    turn = Turn(role="user", text="", timestamp=0.0)

    assert turn.role == "user"
    assert turn.text == ""

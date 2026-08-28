"""Oturum künyesi ve sır sayımı."""

from __future__ import annotations

from datetime import UTC, datetime

from fusion_cli.history.digest import build_digest, count_secrets
from fusion_cli.history.models import SessionRef, Turn


class _FakeSource:
    name = "claude"

    def __init__(self, turns):
        self._turns = turns

    def is_installed(self):
        return True

    def list(self, root=None):
        return ()

    def read(self, session_id, cursor=0, limit=50):
        return tuple(self._turns[cursor : cursor + limit])


def _ref():
    return SessionRef(source="claude", session_id="s1", title="Test", updated_at=0.0, turn_count=2)


def test_digest_lists_user_messages():
    source = _FakeSource(
        [Turn("user", "ilk istek"), Turn("assistant", "cevap"), Turn("user", "ikinci istek")]
    )

    digest = build_digest(source, _ref())

    assert "ilk istek" in digest.text
    assert "ikinci istek" in digest.text


def test_digest_omits_assistant_responses():
    source = _FakeSource([Turn("user", "istek"), Turn("assistant", "uzun ajan cevabı")])

    digest = build_digest(source, _ref())

    assert "uzun ajan cevabı" not in digest.text


def test_digest_is_deterministic():
    source = _FakeSource([Turn("user", "a"), Turn("user", "b")])

    assert build_digest(source, _ref()).text == build_digest(source, _ref()).text


def test_secret_is_counted_without_masking():
    source = _FakeSource([Turn("user", "ANTHROPIC_API_KEY=sk-ant-0123456789abcdefghij")])

    digest = build_digest(source, _ref())

    assert digest.secret_count >= 1
    assert "sk-ant-0123456789abcdefghij" in digest.text


def test_secret_count_is_zero_for_plain_text():
    assert count_secrets("burada hiçbir şey yok") == 0


def test_known_secret_patterns_are_counted():
    assert count_secrets("Bearer abcdefghijklmnopqrstuvwx") >= 1
    assert count_secrets("DB_PASSWORD=cokgizli123") >= 1


def test_digest_scans_secrets_after_first_page() -> None:
    turns = [Turn("assistant", f"yanıt {index}") for index in range(401)]
    turns.append(Turn("user", "DB_PASSWORD=gecici-deger-123"))
    source = _FakeSource(turns)

    digest = build_digest(source, _ref())

    assert digest.secret_count == 1
    assert "tur sayısı: 402" in digest.text


def test_digest_reports_session_date_and_unavailable_file_metadata() -> None:
    updated_at = datetime(2026, 8, 28, tzinfo=UTC).timestamp()
    ref = SessionRef(
        source="claude",
        session_id="s1",
        title="Test",
        updated_at=updated_at,
        turn_count=1,
    )

    digest = build_digest(_FakeSource([Turn("user", "istek")]), ref)

    assert "tarih: 2026-08-28" in digest.text
    assert "dokunulan dosyalar: güvenilir üstveri yok" in digest.text

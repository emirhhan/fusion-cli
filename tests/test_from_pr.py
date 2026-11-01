"""`fusion --from-pr <numara|URL>` (#205)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl import linked_pr, pr_sessions
from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.core.errors import SessionNotFoundError
from fusion_cli.core.pull_request import PullRequestLink


def test_referans_ayristirma():
    assert pr_sessions.parse_reference("123") == (123, None)
    assert pr_sessions.parse_reference("#7") == (7, None)
    assert pr_sessions.parse_reference("https://github.com/Acme/App/pull/42") == (42, "acme/app")
    assert pr_sessions.parse_reference(
        "https://gitlab.com/grup/alt/proje/-/merge_requests/9"
    ) == (9, "grup/alt/proje")
    assert pr_sessions.parse_reference(
        "https://bitbucket.org/ws/repo/pull-requests/3"
    ) == (3, "ws/repo")
    with pytest.raises(SessionNotFoundError):
        pr_sessions.parse_reference("dal-adi")


def _sohbet(memory: Path, root: Path, conv: str, link: PullRequestLink | None) -> None:
    store = TranscriptStore(memory, root, conversation_id=conv)
    store.record_user(f"{conv} istemi")
    linked_pr.save(memory, conv, link)


def test_secici_pr_ye_bagli_sohbetlerle_suzulur(tmp_path: Path):
    memory, root = tmp_path / "bellek", tmp_path / "proje"
    root.mkdir()
    _sohbet(memory, root, "a1", PullRequestLink("acme/app", 42, "https://github.com/acme/app/pull/42"))
    _sohbet(memory, root, "b2", PullRequestLink("acme/app", 43, "u"))
    _sohbet(memory, root, "c3", None)
    gorulen: list[list[str]] = []

    def chooser(choices, title):
        gorulen.append([c.value for c in choices])
        return choices[0].value

    assert pr_sessions.pick_for_pr(memory, root, "42", chooser) == "a1"
    assert gorulen == [["a1"]]
    url = "https://github.com/acme/app/pull/42"
    assert pr_sessions.pick_for_pr(memory, root, url, chooser) == "a1"
    with pytest.raises(SessionNotFoundError, match="PR #99"):
        pr_sessions.pick_for_pr(memory, root, "99", chooser)
    with pytest.raises(SessionNotFoundError):
        pr_sessions.pick_for_pr(memory, root, "42", lambda c, t: None)

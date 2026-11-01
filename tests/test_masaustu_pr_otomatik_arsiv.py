"""Claude Desktop "Auto-archive after PR merge or close": sohbete bağlı PR durumu RPC'si (#443)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver import pr_archive
from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession
from fusion_cli.cli.repl import linked_pr
from fusion_cli.core.pull_request import PullRequestLink


def _link(number: int) -> PullRequestLink:
    return PullRequestLink("o/r", number, f"https://github.com/o/r/pull/{number}")


def test_yalniz_pr_bagli_sohbetler_ve_bilinen_durumlar_doner(tmp_path: Path) -> None:
    linked_pr.save(tmp_path, "a", _link(1))
    linked_pr.save(tmp_path, "b", _link(2))
    linked_pr.save(tmp_path, "c", _link(1))
    seen: list[int] = []

    def reader(link: PullRequestLink) -> str | None:
        seen.append(link.number)
        return {1: "MERGED", 2: None}[link.number]

    states = pr_archive.pr_states(tmp_path, ["a", "b", "c", "yok", 3, ""], reader)

    assert states == {"a": "MERGED", "c": "MERGED"}
    assert sorted(seen) == [1, 2]  # aynı PR bir kez sorulur


def test_gh_yoksa_durum_bilinmez(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr_archive.shutil, "which", lambda name: None)
    assert pr_archive.gh_pr_state(_link(5)) is None


def test_gh_ciktisi_dogrulanir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pr_archive.shutil, "which", lambda name: "/bin/gh")
    calls: list[list[str]] = []

    class Done:
        returncode = 0
        stdout = json.dumps({"state": "CLOSED"})

    def run(command: list[str], **kwargs: object) -> Done:
        calls.append(command)
        return Done()

    monkeypatch.setattr(pr_archive.subprocess, "run", run)
    assert pr_archive.gh_pr_state(_link(7)) == "CLOSED"
    assert calls[0][1:] == ["pr", "view", "7", "--repo", "o/r", "--json", "state"]
    Done.stdout = json.dumps({"state": "garip"})
    assert pr_archive.gh_pr_state(_link(7)) is None


@pytest.mark.asyncio
async def test_rpc_sohbet_pr_durumlari(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lines: list[str] = []
    session = AppSession(lines.append, root=tmp_path, home=tmp_path / "ev")
    linked_pr.save(session._state.config.memory_dir, "s1", _link(9))
    monkeypatch.setattr(pr_archive, "gh_pr_state", lambda link: "MERGED")

    await session.handle(
        Request(id="1", name="sohbet.pr_durumlari", data={"sohbetler": ["s1", "s2"]})
    )

    assert json.loads(lines[-1])["veri"] == {"ok": True, "durumlar": {"s1": "MERGED"}}

"""Devam günlüğünün proje, kilit, boyut ve doğrulanmış meta veri sınırları."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fusion_cli.core.agent_runtime_state import AgentRunState
from fusion_cli.core.types import Message
from fusion_cli.memory import subagent_journal
from fusion_cli.memory.turn_journal_codec import agent_state_from, agent_state_to


def _state(tmp_path, identifier="ajan-1", *, status="completed"):
    return AgentRunState(
        identifier,
        "oturum",
        str(tmp_path.resolve()),
        "yardimci",
        complete_history=True,
        status=status,
        read_only=True,
    )


@pytest.mark.parametrize(
    "field", ["read_only", "tool_names", "denied_tools", "write_scope", "complete_history"]
)
def test_missing_saved_limit_is_never_upgraded_to_authority(tmp_path, field):
    raw = json.loads(json.dumps(agent_state_to(_state(tmp_path))))
    raw.pop(field)
    assert agent_state_from(raw) is None


def test_resume_store_rejects_symlinks_oversize_and_foreign_scope(tmp_path):
    memory = tmp_path / "mem"
    state = _state(tmp_path)
    journal = subagent_journal.agent_journal(memory, tmp_path, "oturum", "ajan-1", state=state)
    journal.save([Message("user", "görev")])
    assert subagent_journal.load_agent(memory, tmp_path, "yabanci", "ajan-1") is None
    journal.path.write_text("x" * (subagent_journal.MAX_JOURNAL_BYTES + 1))
    with pytest.raises(ValueError, match="boyut"):
        subagent_journal.load_agent(memory, tmp_path, "oturum", "ajan-1")
    journal.path.unlink()
    external = tmp_path / "dis.json"
    external.write_text("gizli")
    journal.path.symlink_to(external)
    with pytest.raises(ValueError, match="sembolik"):
        subagent_journal.load_agent(memory, tmp_path, "oturum", "ajan-1")
    assert external.read_text() == "gizli"


async def test_existing_file_lease_serializes_resume_and_releases(tmp_path):
    journal = subagent_journal.agent_journal(tmp_path / "mem", tmp_path, "oturum", "ajan-1")
    async with subagent_journal.agent_lease(journal):
        with pytest.raises(ValueError, match="başka"):
            async with subagent_journal.agent_lease(journal):
                pytest.fail("İkinci sahip girdi.")
    async with subagent_journal.agent_lease(journal):
        pass


def test_retention_bounds_completed_records_but_keeps_active(monkeypatch, tmp_path):
    monkeypatch.setattr(subagent_journal, "MAX_AGENT_RECORDS", 2)
    memory = tmp_path / "mem"
    for index in range(3):
        state = _state(tmp_path, f"ajan-{index}")
        journal = subagent_journal.agent_journal(
            memory, tmp_path, "oturum", state.agent_id, state=state
        )
        journal.save([Message("user", str(index))])
    assert len(list(journal.path.parent.glob("agent-*.json"))) == 2
    for path in journal.path.parent.glob("agent-*.json"):
        raw = json.loads(path.read_text())
        raw["ajan"]["status"] = "running"
        path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="doldu"):
        subagent_journal.agent_journal(
            memory, tmp_path, "oturum", "ajan-4", state=_state(tmp_path, "ajan-4")
        )


async def test_capture_failure_marks_explicit_incomplete(monkeypatch, tmp_path):
    journal = subagent_journal.agent_journal(
        tmp_path / "mem", tmp_path, "oturum", "ajan-1", state=_state(tmp_path)
    )
    capture = subagent_journal.AgentTranscript(journal, complete_history=True)

    def fail(messages):
        raise OSError("yer yok")

    monkeypatch.setattr(journal, "save", fail)
    await capture.begin([Message("user", "Bilinen görev")])
    assert not capture.complete_history and capture.messages[0].content == "Bilinen görev"


def test_named_restore_uses_same_parent_session_and_saved_limits(tmp_path):
    state = replace(_state(tmp_path), name="Belgeler ajanı")
    memory = tmp_path / "mem"
    journal = subagent_journal.agent_journal(
        memory, tmp_path, "oturum", state.agent_id, state=state
    )
    journal.save([Message("user", "özgün görev")])
    entry = subagent_journal.load_agent(memory, tmp_path, "oturum", state.name)
    assert entry.agent_state == state and entry.messages[0].content == "özgün görev"
    assert subagent_journal.load_agent(memory, tmp_path, "başka", state.name) is None

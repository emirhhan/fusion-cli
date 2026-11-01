"""Sürdürmede izin kipi Claude Code'daki yola göre geri gelir (#189).

Belge (sessions.md, "Permission mode on resume"): terminalde `--continue` ve
`--resume <kimlik|tekil ad>` kayıtlı kipi geri yükler (bypass hariç); oturum seçicisi
(`--resume` argümansız, `--from-pr`, belirsiz ad) ve oturum içi `/resume` geçerli kipi
korur, yalnız plan kipinde biten oturum plan kipine döner. `/resume` ile bu süreçte zaten
açılmış bir sohbete dönülürse plan kipi de geri gelmez.
"""

from __future__ import annotations

from pathlib import Path

from fusion_cli.cli.repl import resume_launch, session_clear, session_resume, session_snapshot
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.cli.repl.transcript_store import TranscriptStore
from fusion_cli.core.types import Message
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path: Path, conversation_id: str) -> ReplState:
    root = tmp_path / "proje"
    root.mkdir(exist_ok=True)
    state = ReplState(
        config=make_config(memory_dir=tmp_path / "bellek"),
        memory=null_memory(),
        root=root,
        home=tmp_path / "ev",
    )
    state.conversation_id = conversation_id
    return state


def _saved(tmp_path: Path, conversation_id: str, mode: ApprovalMode) -> None:
    state = _state(tmp_path, conversation_id)
    store = TranscriptStore(state.config.memory_dir, state.root, conversation_id=conversation_id)
    store.record_user("merhaba")
    store.record_assistant("selam")
    state.history = [Message("user", "merhaba"), Message("assistant", "selam")]
    state.approval = mode
    session_snapshot.save(state)


def test_terminal_resume_kimlikle_kayitli_kipi_geri_yukler(tmp_path):
    _saved(tmp_path, "session-abc", ApprovalMode.ACCEPT_EDITS)
    yeni = _state(tmp_path, "session-yeni")
    yeni.approval = ApprovalMode.SECURITY
    target = session_resume.resolve_launch(yeni.config.memory_dir, yeni.root, resume="session-abc")
    assert target is not None
    session_resume.apply_target(yeni, target)
    assert yeni.approval is ApprovalMode.ACCEPT_EDITS


def test_slash_resume_gecerli_kipi_korur(tmp_path):
    _saved(tmp_path, "session-abc", ApprovalMode.ACCEPT_EDITS)
    yeni = _state(tmp_path, "session-yeni")
    yeni.approval = ApprovalMode.SECURITY
    session_resume.resume_command(yeni, "session-abc")
    assert yeni.conversation_id == "session-abc"
    assert yeni.approval is ApprovalMode.SECURITY


def test_slash_resume_dont_ask_kipini_geri_getirmez(tmp_path):
    _saved(tmp_path, "session-abc", ApprovalMode.DONT_ASK)
    yeni = _state(tmp_path, "session-yeni")
    yeni.approval = ApprovalMode.AUTO
    session_resume.resume_command(yeni, "session-abc")
    assert yeni.approval is ApprovalMode.AUTO


def test_slash_resume_plan_kipinde_biten_sohbeti_plana_dondurur(tmp_path):
    _saved(tmp_path, "session-abc", ApprovalMode.PLAN)
    yeni = _state(tmp_path, "session-yeni")
    yeni.approval = ApprovalMode.SECURITY
    session_resume.resume_command(yeni, "session-abc")
    assert yeni.approval is ApprovalMode.PLAN


def test_slash_resume_bu_surecte_acilmis_sohbete_donunce_plani_geri_getirmez(tmp_path):
    _saved(tmp_path, "session-abc", ApprovalMode.PLAN)
    state = _state(tmp_path, "session-abc")
    state.approval = ApprovalMode.SECURITY
    session_clear.clear_command(state, "")
    session_resume.resume_command(state, "session-abc")
    assert state.conversation_id == "session-abc"
    assert state.approval is ApprovalMode.SECURITY


def test_seciciden_secilen_oturum_yalniz_plani_geri_yukler(tmp_path, monkeypatch):
    _saved(tmp_path, "session-abc", ApprovalMode.ACCEPT_EDITS)
    _saved(tmp_path, "session-plan", ApprovalMode.PLAN)
    yeni = _state(tmp_path, "session-yeni")
    yeni.approval = ApprovalMode.SECURITY
    monkeypatch.setattr(resume_launch, "_claude_picker", lambda memory, root: "session-abc")
    target = session_resume.resolve_launch(
        yeni.config.memory_dir, yeni.root, resume=resume_launch.RESUME_PICKER
    )
    assert target is not None
    session_resume.apply_target(yeni, target)
    assert yeni.conversation_id == "session-abc"
    assert yeni.approval is ApprovalMode.SECURITY

    plan = _state(tmp_path, "session-yeni2")
    plan.approval = ApprovalMode.SECURITY
    monkeypatch.setattr(resume_launch, "_claude_picker", lambda memory, root: "session-plan")
    target = session_resume.resolve_launch(
        plan.config.memory_dir, plan.root, resume=resume_launch.RESUME_PICKER
    )
    assert target is not None
    session_resume.apply_target(plan, target)
    assert plan.approval is ApprovalMode.PLAN


def test_from_pr_secicisi_kayitli_kipi_geri_yuklemez(tmp_path):
    _saved(tmp_path, "session-abc", ApprovalMode.ACCEPT_EDITS)
    yeni = _state(tmp_path, "session-yeni")
    yeni.approval = ApprovalMode.SECURITY
    target = session_resume.resolve_launch(
        yeni.config.memory_dir, yeni.root, resume="session-abc", via_picker=True
    )
    assert target is not None
    session_resume.apply_target(yeni, target)
    assert yeni.approval is ApprovalMode.SECURITY

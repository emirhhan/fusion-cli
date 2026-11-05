"""Desired accepted execution binding; currently known pre-existing lifecycle defects."""

import asyncio
import threading

import pytest

from fusion_cli.appserver.protocol import Request
from fusion_cli.engines.agent.loop import AgentOutcome
from tests.test_appserver_session import _session


@pytest.mark.parametrize("boundary", ["prestart", "memory"])
async def test_accepted_execution_keeps_root_and_conversation(tmp_path, monkeypatch, boundary):
    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    seen = []

    async def run(*args, **kwargs):
        seen.append((kwargs["root"].resolve(), kwargs["conversation_id"]))
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    entered, release = asyncio.Event(), asyncio.Event()
    thread_entered, thread_release = threading.Event(), threading.Event()
    if boundary == "prestart":
        original = session._submission_store.finish

        async def finish(*args, **kwargs):
            if kwargs.get("state") == "running":
                entered.set()
                await release.wait()
            return await original(*args, **kwargs)

        monkeypatch.setattr(session._submission_store, "finish", finish)
    else:

        def memory():
            thread_entered.set()
            assert thread_release.wait(5)
            return ""

        monkeypatch.setattr(session._personal_memory, "prompt_block", memory)
    pending = asyncio.create_task(
        session._dispatch(
            Request(
                "r",
                "tur.calistir",
                {"gorev": "Kısa HTML raporunu rapor.html olarak hazırla.", "gonderim_id": "job"},
            )
        )
    )
    try:
        if boundary == "prestart":
            await asyncio.wait_for(entered.wait(), 3)
        else:
            assert await asyncio.to_thread(thread_entered.wait, 3)
        other = tmp_path / "other"
        other.mkdir()
        data = {"sohbet_id": "new", **({"kok": str(other)} if boundary == "prestart" else {})}
        assert (await session._dispatch(Request("switch", "oturum.baslat", data)))["ok"]
    finally:
        release.set()
        thread_release.set()
    await asyncio.wait_for(pending, 5)
    await session.close()
    assert seen == [(tmp_path.resolve(), "accepted")]


async def test_admission_captures_config_and_history_before_claim(tmp_path, monkeypatch):
    from dataclasses import replace

    from fusion_cli.core.types import Message

    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    session._state.history = [Message("assistant", "accepted history")]
    accepted_config = session._state.config
    entered, release = asyncio.Event(), asyncio.Event()
    original = session._submission_store.claim

    async def claim(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(session._submission_store, "claim", claim)
    seen = []

    async def run(task, config, **kwargs):
        seen.append((config, list(kwargs["history"])))
        return AgentOutcome("old done", [Message("assistant", "old done")])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    pending = asyncio.create_task(
        session._dispatch(
            Request("r", "tur.calistir", {"gorev": "Eski işi tamamla", "gonderim_id": "job"})
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    manual = replace(accepted_config, agent=replace(accepted_config.agent, model="manual-new"))
    session._state.config = manual
    await session._dispatch(Request("switch", "oturum.baslat", {"sohbet_id": "new"}))
    session._state.history = [Message("assistant", "new history")]
    release.set()
    await asyncio.wait_for(pending, 5)
    assert seen == [(accepted_config, [Message("assistant", "accepted history")])]
    assert session._state.config is manual
    assert session._state.history == [Message("assistant", "new history")]
    await session.close()


@pytest.mark.parametrize("return_to_owner", [False, True])
async def test_tools_and_completion_stay_with_accepted_chat(tmp_path, monkeypatch, return_to_owner):
    from fusion_cli.core.events import ToolExecuted, ToolOutcome
    from fusion_cli.core.types import Message
    from tests.test_document_delivery_presentation import TASK, report_outcome

    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    entered, release = asyncio.Event(), asyncio.Event()
    outcome, clean_text = report_outcome()
    outcome.messages = [Message("user", TASK), Message("assistant", outcome.final_text)]

    async def run(task, config, **kwargs):
        entered.set()
        await release.wait()
        kwargs["sinks"][0].handle(
            ToolExecuted(
                "read_file",
                {"path": "rapor.html"},
                ToolOutcome.OK,
                "accepted tool output",
                call_id="accepted-call",
            )
        )
        return outcome

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    pending = asyncio.create_task(
        session._dispatch(Request("r", "tur.calistir", {"gorev": TASK, "gonderim_id": "job"}))
    )
    await asyncio.wait_for(entered.wait(), 3)
    await session._dispatch(Request("new", "oturum.baslat", {"sohbet_id": "new"}))
    session._state.history = [Message("assistant", "new history")]
    if return_to_owner:
        await session._dispatch(Request("old", "oturum.baslat", {"sohbet_id": "accepted"}))
    release.set()
    result = await asyncio.wait_for(pending, 5)
    if not return_to_owner:
        assert session._state.history == [Message("assistant", "new history")]
        assert (await session._dispatch(Request("h", "oturum.gecmis", {})))["mesajlar"] == [
            {"rol": "asistan", "metin": "new history"}
        ]
        await session._dispatch(Request("old", "oturum.baslat", {"sohbet_id": "accepted"}))
    rows = (await session._dispatch(Request("h", "oturum.gecmis", {})))["mesajlar"]
    answers = [row for row in rows if row["rol"] == "asistan"]
    assert len(answers) == 1 and answers[0]["metin"] == clean_text
    assert answers[0]["kanit"] == result["kanit"]
    assert any(row["rol"] == "olay" for row in rows)
    assert session._state.history[-1].content == clean_text
    await session.close()


async def test_pending_inputs_are_not_replayed_or_stolen(tmp_path, monkeypatch):
    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    session._state.pending_context = "accepted skill context"
    entered, release = asyncio.Event(), asyncio.Event()
    original = session._submission_store.claim

    async def claim(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(session._submission_store, "claim", claim)
    seen = []

    async def run(task, config, **kwargs):
        seen.append(kwargs["extra_system"])
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    request = Request("r", "tur.calistir", {"gorev": "İşi bitir", "gonderim_id": "job"})
    pending = asyncio.create_task(session._dispatch(request))
    await asyncio.wait_for(entered.wait(), 3)
    await session._dispatch(Request("new", "oturum.baslat", {"sohbet_id": "new"}))
    assert session._state.pending_context == ""
    session._state.pending_context = "new skill context"
    release.set()
    await asyncio.wait_for(pending, 5)
    assert "accepted skill context" in seen[0] and "new skill context" not in seen[0]
    assert session._state.pending_context == "new skill context"
    await session._dispatch(Request("old", "oturum.baslat", {"sohbet_id": "accepted"}))
    session._state.pending_context = "next context"
    await session._dispatch(request)  # Cached receipt must not consume next-turn input.
    assert session._state.pending_context == "next context" and len(seen) == 1
    await session.close()


async def test_session_consent_and_root_writer_follow_accepted_owner(tmp_path, monkeypatch):
    from pathlib import Path

    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    calls, roots = [], []
    entered, release = asyncio.Event(), asyncio.Event()

    def remember(root, request):
        roots.append(Path(root).resolve())
        return "saved"

    monkeypatch.setattr("fusion_cli.cli.rule_notices.remember_always", remember)

    async def run(task, config, **kwargs):
        memory = kwargs["approval_memory"]
        calls.append(memory.scopes_with_prefix("chrome-site:"))
        memory._scopes.add("chrome-site:example.com")
        if len(calls) == 2:
            entered.set()
            await release.wait()
            memory.rule_writer(object())
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session._dispatch(
        Request("r1", "tur.calistir", {"gorev": "İlk iş", "gonderim_id": "one"})
    )
    assert session._state.approval_memory.scopes_with_prefix("chrome-site:") == [
        "chrome-site:example.com"
    ]
    pending = asyncio.create_task(
        session._dispatch(
            Request("r2", "tur.calistir", {"gorev": "İkinci iş", "gonderim_id": "two"})
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    await session._dispatch(Request("switch", "oturum.baslat", {"sohbet_id": "new"}))
    release.set()
    await asyncio.wait_for(pending, 5)
    assert calls == [[], ["chrome-site:example.com"]]
    assert roots == [tmp_path.resolve()]
    await session.close()


async def test_legacy_turn_uses_snapshot_after_memory_await(tmp_path, monkeypatch):
    from fusion_cli.core.types import Message

    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    entered, release = threading.Event(), threading.Event()
    seen = []

    def memory():
        entered.set()
        assert release.wait(5)
        return ""

    monkeypatch.setattr(session._personal_memory, "prompt_block", memory)

    async def run(task, config, **kwargs):
        seen.append(kwargs["conversation_id"])
        return AgentOutcome("legacy done", [Message("assistant", "legacy done")])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    pending = asyncio.create_task(session._run_turn("Eski protokol işi"))
    assert await asyncio.to_thread(entered.wait, 3)
    await session._dispatch(Request("new", "oturum.baslat", {"sohbet_id": "new"}))
    release.set()
    await asyncio.wait_for(pending, 5)
    assert seen == ["accepted"] and session._state.history == []
    await session.close()


async def test_stored_todos_do_not_rebind_to_new_visible_chat(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.task_list import session_todos, task_list_path
    from fusion_cli.core.tools import TodoItem, TodoStatus

    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    session_todos(session._state, new_turn=False)
    memory_dir = session._state.config.memory_dir
    entered, release = asyncio.Event(), asyncio.Event()

    async def run(task, config, **kwargs):
        entered.set()
        await release.wait()
        kwargs["todos"].replace((TodoItem("owned todo", TodoStatus.COMPLETED),))
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    pending = asyncio.create_task(
        session._dispatch(
            Request("r", "tur.calistir", {"gorev": "İşi bitir", "gonderim_id": "job"})
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    await session._dispatch(Request("new", "oturum.baslat", {"sohbet_id": "new"}))
    release.set()
    await asyncio.wait_for(pending, 5)
    assert task_list_path(memory_dir, "accepted").exists()
    assert not task_list_path(memory_dir, "new").exists()
    await session.close()


async def test_local_shell_output_survives_with_newly_queued_context(tmp_path, monkeypatch):
    from fusion_cli.cli.repl.prefixes import ShellPrefixResult, push_pending_context

    session = _session(tmp_path, [])
    entered, release = asyncio.Event(), asyncio.Event()

    async def shell(state, command, **kwargs):
        entered.set()
        await release.wait()
        push_pending_context(state, "accepted shell output")
        return ShellPrefixResult("output", True, "accepted shell output")

    monkeypatch.setattr("fusion_cli.cli.repl.prefixes.run_shell_prefix", shell)
    pending = asyncio.create_task(session._run_turn("! example"))
    await asyncio.wait_for(entered.wait(), 3)
    push_pending_context(session._state, "newly queued context")
    release.set()
    await asyncio.wait_for(pending, 5)
    assert session._state.pending_blocks == ["newly queued context", "accepted shell output"]
    await session.close()


async def test_same_chat_pr_badge_is_adopted(tmp_path, monkeypatch):
    from fusion_cli.core.pull_request import PullRequestLink

    session = _session(tmp_path, [])
    link = PullRequestLink("example/repo", 1, "https://github.com/example/repo/pull/1")
    monkeypatch.setattr(
        "fusion_cli.cli.repl.linked_pr.bind_from_turn",
        lambda state, uses: setattr(state, "linked_pr", link),
    )

    async def run(*args, **kwargs):
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session._run_turn("İşi bitir")
    assert session._state.linked_pr == link
    await session.close()


async def test_pending_startup_hook_keeps_verdict_context_and_owner(tmp_path, monkeypatch):
    from fusion_cli.core.hooks.events import HookVerdict
    from fusion_cli.engines.hooks.opening import settle_opening

    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    source = session._state.hooks()
    source.started = True
    entered, release = asyncio.Event(), asyncio.Event()

    async def opening():
        await release.wait()
        source.add_start_context("startup context")
        return HookVerdict(system_messages=("startup notice",))

    original = source.opening = asyncio.create_task(opening())
    seen = []

    async def run(task, config, **kwargs):
        hooks = kwargs["hooks"]
        entered.set()
        verdict = await settle_opening(hooks)
        seen.append(
            (
                hooks is source,
                verdict.system_messages,
                hooks.take_start_context(),
                hooks.conversation_id,
            )
        )
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    pending = asyncio.create_task(
        session._dispatch(
            Request("r", "tur.calistir", {"gorev": "İşi bitir", "gonderim_id": "job"})
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    await session._dispatch(Request("new", "oturum.baslat", {"sohbet_id": "new"}))
    release.set()
    await asyncio.wait_for(pending, 5)
    await original
    assert seen == [(True, ("startup notice",), "startup context", "accepted")]
    assert session._state.hook_session is not source
    await session.close()


async def test_goal_judgement_cannot_update_new_visible_chat(tmp_path, monkeypatch):
    from types import SimpleNamespace

    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    session._state.goal = SimpleNamespace(is_active=True)
    entered, release = asyncio.Event(), asyncio.Event()
    accepted_goal = object()

    async def goal(state, **kwargs):
        entered.set()
        await release.wait()
        state.goal = accepted_goal
        return SimpleNamespace(next_prompt="accepted continuation")

    async def run(*args, **kwargs):
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    monkeypatch.setattr("fusion_cli.cli.repl.goal_flow.evaluate_goal", goal)
    monkeypatch.setattr("fusion_cli.cli.repl.goal_flow.wire_payload", lambda outcome, state: {})
    pending = asyncio.create_task(
        session._dispatch(
            Request("r", "tur.calistir", {"gorev": "İşi bitir", "gonderim_id": "job"})
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    await session._dispatch(Request("new", "oturum.baslat", {"sohbet_id": "new"}))
    release.set()
    await asyncio.wait_for(pending, 5)
    assert session._state.goal is None and session._goal_continuation is None
    await session.close()


async def test_claim_failure_releases_hook_lease_without_consuming_startup(tmp_path, monkeypatch):
    from dataclasses import replace

    from fusion_cli.core.hooks.events import HookVerdict

    session = _session(tmp_path, [])
    source = session._state.hooks()
    startup = source.opening = asyncio.create_task(asyncio.sleep(0, result=HookVerdict()))

    async def claim(*args, **kwargs):
        raise OSError("fixture storage failure")

    monkeypatch.setattr(session._submission_store, "claim", claim)
    session._state.pending_context = "next context"
    result = await session._dispatch(
        Request("r", "tur.calistir", {"gorev": "İşi bitir", "gonderim_id": "job"})
    )
    assert not result["ok"] and session._hook_lease is None
    assert source.opening is startup and session._state.pending_context == "next context"
    session._state.config = replace(
        session._state.config,
        agent=replace(session._state.config.agent, model="manual-after-failure"),
    )
    assert source.model() == "manual-after-failure"
    await startup
    await session.close()


async def test_live_permission_revocation_clears_accepted_consent(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.approval import ApprovalMode

    session = _session(tmp_path, [])
    session._state.approval = ApprovalMode.AUTO
    session._state.approval_memory._scopes.add("chrome-site:example.com")
    entered, release = asyncio.Event(), asyncio.Event()
    seen = []

    async def run(task, config, **kwargs):
        entered.set()
        await release.wait()
        seen.append(
            (
                kwargs["current_approval"](),
                kwargs["approval_memory"].scopes_with_prefix("chrome-site:"),
            )
        )
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    pending = asyncio.create_task(
        session._dispatch(
            Request("r", "tur.calistir", {"gorev": "İşi bitir", "gonderim_id": "job"})
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    assert session._apply_mode("security", persist=False) is None
    release.set()
    await asyncio.wait_for(pending, 5)
    assert seen == [(ApprovalMode.SECURITY, [])]
    await session.close()


@pytest.mark.parametrize("action", ["forget", "after_auto"])
async def test_live_explicit_permission_change_overrides_snapshot(tmp_path, monkeypatch, action):
    from fusion_cli.engines.agent.approval import ApprovalMode
    from fusion_cli.engines.agent.auto_switch import apply_auto_switch

    session = _session(tmp_path, [])
    session._state.approval = ApprovalMode.SECURITY
    scope = "chrome-site:example.com"
    session._state.approval_memory._scopes.add(scope)
    entered, release = asyncio.Event(), asyncio.Event()
    seen = []

    async def run(task, config, **kwargs):
        if action == "after_auto":
            apply_auto_switch(kwargs["approval_memory"])
        entered.set()
        await release.wait()
        mode = kwargs["current_approval"]()
        seen.append((mode, kwargs["approval_memory"].scopes_with_prefix("chrome-site:")))
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    monkeypatch.setattr("fusion_cli.config.browser_sites.load_allowed", lambda: frozenset())
    pending = asyncio.create_task(
        session._dispatch(
            Request("r", "tur.calistir", {"gorev": "İşi bitir", "gonderim_id": "job"})
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    if action == "forget":
        assert (await session._chrome_settings({"izin_sil": scope}))["ok"]
    else:
        assert session._state.approval is ApprovalMode.AUTO
        assert session._apply_mode("security", persist=False) is None
    release.set()
    await asyncio.wait_for(pending, 5)
    assert seen == [(ApprovalMode.SECURITY, [])]
    await session.close()


async def test_browser_panel_keeps_consent_without_touching_chat_history(tmp_path, monkeypatch):
    from fusion_cli.core.types import Message

    session = _session(tmp_path, [])
    session._state.history = [Message("assistant", "main history")]
    seen = []

    async def run(task, config, **kwargs):
        memory = kwargs["approval_memory"]
        seen.append(memory.scopes_with_prefix("chrome-site:"))
        memory._scopes.add("chrome-site:example.com")
        return AgentOutcome("panel done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session._chrome_turn("İlk panel işi")
    await session._chrome_turn("İkinci panel işi")
    assert seen == [[], ["chrome-site:example.com"]]
    assert session._state.history == [Message("assistant", "main history")]
    await session.close()


async def test_permission_callback_uses_accepted_config_after_switch(tmp_path, monkeypatch):
    from dataclasses import replace

    session = _session(tmp_path, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    accepted_model = session._state.config.agent.model
    entered, release = asyncio.Event(), asyncio.Event()
    seen = []

    def deny(config, app):
        seen.append(config.agent.model)
        return {"ok": True}, config

    async def run(task, config, **kwargs):
        entered.set()
        await release.wait()
        prompter = kwargs["prompter_factory"](None)
        await prompter._on_app_denied("Mail")
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    monkeypatch.setattr("fusion_cli.appserver.computer_routes.deny_app", deny)
    pending = asyncio.create_task(
        session._dispatch(
            Request("r", "tur.calistir", {"gorev": "İşi bitir", "gonderim_id": "job"})
        )
    )
    await asyncio.wait_for(entered.wait(), 3)
    await session._dispatch(Request("new", "oturum.baslat", {"sohbet_id": "new"}))
    session._state.config = replace(
        session._state.config, agent=replace(session._state.config.agent, model="new-visible")
    )
    release.set()
    await asyncio.wait_for(pending, 5)
    assert seen == [accepted_model] and session._state.config.agent.model == "new-visible"
    await session.close()


async def test_auto_offer_then_classifier_fallback_stays_manual(tmp_path, monkeypatch):
    from fusion_cli.engines.agent.approval import ApprovalMode
    from fusion_cli.engines.agent.auto_switch import apply_auto_switch

    session = _session(tmp_path, [])
    session._state.approval = ApprovalMode.SECURITY
    seen = []

    async def run(task, config, **kwargs):
        memory = kwargs["approval_memory"]
        apply_auto_switch(memory)
        memory.auto_review.on_fallback()
        memory._scopes.add("chrome-site:example.com")
        seen.append(kwargs["current_approval"]())
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session._run_turn("İşi bitir")
    assert seen == [ApprovalMode.SECURITY] and session._state.approval is ApprovalMode.SECURITY
    assert session._state.approval_memory.scopes_with_prefix("chrome-site:") == [
        "chrome-site:example.com"
    ]
    await session.close()


async def test_symlink_root_preserves_same_owner_state_and_pending_inputs(tmp_path, monkeypatch):
    from fusion_cli.core.types import Message

    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    session = _session(alias, [])
    await session._dispatch(Request("s", "oturum.baslat", {"sohbet_id": "accepted"}))
    session._state.pending_context = "accepted context"
    seen = []

    async def run(task, config, **kwargs):
        seen.append(kwargs["root"])
        return AgentOutcome("done", [Message("assistant", "done")])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    await session._run_turn("İşi bitir")
    assert seen == [real.resolve()]
    assert session._state.history == [Message("assistant", "done")]
    assert session._state.pending_context == ""
    await session.close()


async def test_cached_receipt_preserves_live_hook_identity_and_pending_input(tmp_path, monkeypatch):
    from fusion_cli.core.hooks.events import HookVerdict

    session = _session(tmp_path, [])
    source = session._state.hooks()

    async def run(*args, **kwargs):
        return AgentOutcome("done", [])

    monkeypatch.setattr("fusion_cli.cli.session.run_agent_task", run)
    request = Request("r", "tur.calistir", {"gorev": "İşi bitir", "gonderim_id": "job"})
    await session._dispatch(request)
    source = session._state.hook_session
    watcher = source.watcher = object()
    startup = source.opening = asyncio.create_task(asyncio.sleep(0, result=HookVerdict()))
    source._background.add(startup)
    session._state.pending_context = "next input"
    replay = await session._dispatch(request)
    assert replay["metin"] == "" and session._hook_lease is None
    assert session._state.hook_session is source
    assert source.watcher is watcher and source.opening is startup and startup in source._background
    assert session._state.pending_context == "next input"
    await startup
    source._background.clear()
    await session.close()

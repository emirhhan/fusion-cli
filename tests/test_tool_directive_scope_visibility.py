from __future__ import annotations

from fusion_cli.cli import session
from fusion_cli.core.events import ErrorOccurred
from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.execution_policy import (
    _explicit_no_tools,
    policy_for,
)
from fusion_cli.engines.agent.loop import AgentOutcome

from .fakes import RecordingSink, make_config

A2_TASK = """
Toplam tam olarak 1 adet write_file çağrısı yap.
Toplam tam olarak 1 adet read_file çağrısı yap.
Başka hiçbir araç çağrısı yapma.
live_test_a2/input.txt dosyasını oluştur.
Dosyayı bir kez oku.
read_file çağrısından sonra hiçbir araç kullanma.
"""


def test_scoped_no_tool_directives_do_not_disable_requested_tools() -> None:
    assert _explicit_no_tools(A2_TASK.lower()) is False

    config = make_config(agent=ModelSpec(name="agent", model="gemini_web/main/auto"))
    policy = policy_for(
        config,
        config.agent,
        TaskKind.GENERAL,
        A2_TASK,
    )

    assert policy.offer_tools is True
    assert policy.requires_tool_evidence is True
    assert policy.required_effect == "workspace_mutation"


def test_global_no_tool_directive_still_disables_tools() -> None:
    task = "Repoyu GitHub'a pushla ama araç kullanma."
    assert _explicit_no_tools(task.lower()) is True

    config = make_config(agent=ModelSpec(name="agent", model="gemini_web/main/auto"))
    policy = policy_for(
        config,
        config.agent,
        TaskKind.GENERAL,
        task,
    )

    assert policy.offer_tools is False
    assert policy.requires_tool_evidence is True
    assert policy.required_effect == "git_push"


class _Prompter:
    async def confirm(self, _request: object) -> bool:
        return True

    async def ask(self, _question: str) -> str:
        return ""


def _prompter_factory(_drain):
    return _Prompter()


async def test_agent_session_surfaces_non_rate_failure(
    monkeypatch,
    tmp_path,
) -> None:
    async def fake_run_agent(
        _task,
        _deps,
        *,
        history=None,
        plan_mode=False,
        extra_system=None,
    ):
        del history, plan_mode, extra_system
        return AgentOutcome(
            final_text="İşlem tamamlanmadı: gerekli araç kanıtı yok.",
            messages=[Message("user", "görev")],
            ok=False,
        )

    monkeypatch.setattr(session, "run_agent", fake_run_agent)
    sink = RecordingSink()

    outcome = await session.run_agent_task(
        "görev",
        make_config(runtime={"lessons": False}),
        sinks=(sink,),
        prompter_factory=_prompter_factory,
        root=tmp_path,
        interactive=False,
    )

    errors = [event for event in sink.events if isinstance(event, ErrorOccurred)]
    assert outcome.ok is False
    assert errors
    assert errors[-1].message == outcome.final_text
    assert errors[-1].fatal is False

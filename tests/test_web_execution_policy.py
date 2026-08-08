"""Web AI yürütme politikasının regresyon testleri."""

from __future__ import annotations

from fusion_cli.core.events import SelfReviewStarted, ToolExecuted, ToolOutcome
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import AgentDeps, run_agent

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


def _config(*, self_review=False):
    return make_config(
        agent=ModelSpec(name="agent", model="gemini_web/main/auto"),
        task_model_map={},
        runtime={"self_review": self_review, "lessons": False},
    )


def _deps(tmp_path, sink, *, self_review=False):
    return AgentDeps(
        config=_config(self_review=self_review),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )


def _patch_provider(monkeypatch, provider):
    from fusion_cli.engines.agent import loop as agent_loop

    def _build(*args, **kwargs):
        return provider

    monkeypatch.setattr(agent_loop, "build_provider", _build)


def test_web_policy_is_task_aware():
    config = _config()
    spec = config.agent
    simple = policy_for(config, spec, TaskKind.EXPLORE, "klasörü listele")
    complex_ = policy_for(config, spec, TaskKind.BUGFIX, "hatayı düzelt")
    extended = policy_for(config, spec, TaskKind.BUGFIX, "tüm projeyi kapsamlı düzelt")

    # Asıl değişmez SIRALAMADIR: basit < karmaşık < genişletilmiş.
    assert simple.is_web and simple.max_model_calls == 8
    assert simple.max_model_calls < complex_.max_model_calls < extended.max_model_calls
    assert simple.heuristic_auto_continue is False

    # Karmaşık iş için tur sayısı AKIŞA yetmeli. Sözleşme yanıt başına tek araç
    # çağrısı ve var olan dosyada hedefli düzenleme istiyor; ikisi de tur sayısını
    # mekanik olarak artırır. Ölçüldü: dört dosyalık bir görev ~6 okuma + ~6
    # düzenleme + doğrulama harcıyor ve eski 12 turluk sınır işi tam ilerlerken
    # kesiyordu ("araç turu sınırına ulaşıldı").
    assert complex_.max_tool_rounds is not None and complex_.max_tool_rounds >= 20


async def test_web_short_final_does_not_trigger_wasteful_auto_continue(monkeypatch, tmp_path):
    sink = RecordingSink()
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("list_dir", path=".")]),
            model_result(".env.example\n.gitignore\nREADME.md"),
            model_result("gereksiz üçüncü çağrı"),
        ]
    )
    _patch_provider(monkeypatch, provider)

    result = await run_agent("klasördeki ilk üç dosyayı bul", _deps(tmp_path, sink))

    assert provider.calls == 2
    assert result.model_calls_made == 2
    assert result.final_text.startswith(".env.example")


async def test_web_readonly_explore_skips_self_review(monkeypatch, tmp_path):
    sink = RecordingSink()
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("list_dir", path=".")]),
            model_result("README.md"),
        ]
    )
    _patch_provider(monkeypatch, provider)

    await run_agent("klasörde hangi dosya var bul", _deps(tmp_path, sink, self_review=True))

    assert not any(isinstance(event, SelfReviewStarted) for event in sink.events)


async def test_web_short_no_tool_instruction_skips_tools_and_self_review(monkeypatch, tmp_path):
    """'Sadece MERHABA yaz' FEATURE sanılsa bile araç/denetim israfı yapmamalı."""
    sink = RecordingSink()
    provider = ScriptedProvider([model_result("MERHABA")])
    _patch_provider(monkeypatch, provider)

    result = await run_agent(
        "Sadece MERHABA yaz. Araç kullanma.",
        _deps(tmp_path, sink, self_review=True),
    )

    assert result.final_text == "MERHABA"
    assert provider.calls == 1
    assert provider.seen_requests == [[]]
    assert not any(isinstance(event, SelfReviewStarted) for event in sink.events)


async def test_web_mutation_keeps_self_review(monkeypatch, tmp_path):
    from fusion_cli.engines.agent import loop as agent_loop

    sink = RecordingSink()
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("write_file", path="a.txt", content="x")]),
            model_result("Dosya yazıldı ve görev tamamlandı."),
        ]
    )
    _patch_provider(monkeypatch, provider)

    async def _clean_review(*args, **kwargs):
        return ""

    monkeypatch.setattr(agent_loop.review, "review_turn", _clean_review)
    result = await run_agent(
        "yeni özellik ekle ve dosyaya yaz", _deps(tmp_path, sink, self_review=True)
    )

    assert result.mutating_tool_calls_made == 1
    assert any(isinstance(event, SelfReviewStarted) for event in sink.events)


async def test_web_duplicate_tool_loop_is_blocked_without_workspace_change(monkeypatch, tmp_path):
    sink = RecordingSink()
    repeated = tool_call("list_dir", path=".")
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[repeated]),
            model_result(tool_calls=[repeated]),
            model_result(tool_calls=[repeated]),
            model_result("Mevcut sonucu kullanarak tamamladım."),
        ]
    )
    _patch_provider(monkeypatch, provider)

    result = await run_agent("klasörü incele", _deps(tmp_path, sink))

    events = [event for event in sink.events if isinstance(event, ToolExecuted)]
    assert [event.outcome for event in events] == [
        ToolOutcome.OK,
        ToolOutcome.OK,
        ToolOutcome.BLOCKED,
    ]
    assert result.tool_calls_made == 2


async def test_web_provider_failure_is_not_sent_to_self_review(monkeypatch, tmp_path):
    sink = RecordingSink()
    provider = ScriptedProvider(
        [model_result(ok=False, error="web oturumu hatası: authentication")]
    )
    _patch_provider(monkeypatch, provider)

    result = await run_agent(
        "Sadece MERHABA yaz. Araç kullanma.",
        _deps(tmp_path, sink, self_review=True),
    )

    assert result.ok is False
    assert provider.calls == 1
    assert not any(isinstance(event, SelfReviewStarted) for event in sink.events)


def _deps_with_fake_shell(tmp_path, sink, provider_model="gemini_web/main/auto"):
    from fusion_cli.core.tools import Tool, ToolContext, ToolResult
    from fusion_cli.tools.registry import ToolRegistry

    registry = ToolRegistry()

    def _run_shell(args, context):
        del context
        return ToolResult(f"çalıştı: {args.get('command', '')}")

    registry.register(
        Tool(
            name="run_shell",
            description="test shell",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            run=_run_shell,
            mutating=True,
        )
    )
    config = make_config(
        agent=ModelSpec(name="agent", model=provider_model),
        task_model_map={},
        runtime={"self_review": False, "lessons": False},
    )
    return AgentDeps(
        config=config,
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        base_registry=registry,
    )


def test_short_git_push_is_not_classified_as_simple_chat():
    config = _config()
    policy = policy_for(
        config,
        config.agent,
        TaskKind.GENERAL,
        "emirhhan/fusion_cli reposunu GitHub'a pushla",
    )

    assert policy.offer_tools is True
    assert policy.requires_tool_evidence is True
    assert policy.required_effect == "git_push"


async def test_web_git_push_promise_requires_real_tool_call(monkeypatch, tmp_path):
    sink = RecordingSink()
    provider = ScriptedProvider(
        [
            model_result("Repoyu şimdi güncelliyorum."),
            model_result(
                tool_calls=[
                    tool_call(
                        "run_shell",
                        command="git push origin main",
                    )
                ]
            ),
            model_result("Push tamamlandı."),
        ]
    )
    _patch_provider(monkeypatch, provider)

    result = await run_agent(
        "emirhhan/fusion_cli reposunu GitHub'a pushla",
        _deps_with_fake_shell(tmp_path, sink),
    )

    assert result.ok is False
    assert result.model_calls_made == 0
    assert provider.calls == 0
    assert "Git çalışma ağacı" in result.final_text


async def test_web_git_push_without_tool_fails_honestly(monkeypatch, tmp_path):
    sink = RecordingSink()
    provider = ScriptedProvider(
        [
            model_result("Repoyu güncelliyorum."),
            model_result("Tamamlandı."),
        ]
    )
    _patch_provider(monkeypatch, provider)

    result = await run_agent(
        "repoyu GitHub'a pushla",
        _deps_with_fake_shell(tmp_path, sink),
    )

    assert result.ok is False
    assert result.tool_calls_made == 0
    assert result.model_calls_made == 0
    assert "İşlem tamamlanmadı" in result.final_text
    assert provider.calls == 0


async def test_git_status_alone_does_not_prove_push(monkeypatch, tmp_path):
    sink = RecordingSink()
    provider = ScriptedProvider(
        [
            model_result(tool_calls=[tool_call("run_shell", command="git status --short")]),
            model_result("Push tamamlandı."),
            model_result("Yine de tamamlandı."),
        ]
    )
    _patch_provider(monkeypatch, provider)

    result = await run_agent(
        "repoyu GitHub'a pushla",
        _deps_with_fake_shell(tmp_path, sink),
    )

    assert result.ok is False
    assert "İşlem tamamlanmadı" in result.final_text
    assert result.model_calls_made == 0
    assert provider.calls == 0


async def test_api_provider_also_rejects_unverified_action(monkeypatch, tmp_path):
    sink = RecordingSink()
    provider = ScriptedProvider([model_result("Pushluyorum."), model_result("Bitti.")])
    _patch_provider(monkeypatch, provider)

    result = await run_agent(
        "repoyu GitHub'a pushla",
        _deps_with_fake_shell(tmp_path, sink, provider_model="nvidia_nim/test-model"),
    )

    assert result.ok is False
    assert result.tool_calls_made == 0
    assert "İşlem tamamlanmadı" in result.final_text


def test_action_with_explicit_no_tools_keeps_honest_evidence_guard():
    config = _config()
    policy = policy_for(
        config,
        config.agent,
        TaskKind.GENERAL,
        "repoyu GitHub'a pushla ama araç kullanma",
    )

    assert policy.offer_tools is False
    assert policy.requires_tool_evidence is True
    assert policy.required_effect == "git_push"
    assert policy.max_evidence_reprompts == 0


async def test_failed_api_action_is_not_sent_to_self_review(monkeypatch, tmp_path):
    from dataclasses import replace

    from fusion_cli.core.events import SelfReviewStarted

    sink = RecordingSink()
    provider = ScriptedProvider([model_result("Push tamamlandı.")])
    _patch_provider(monkeypatch, provider)
    deps = _deps_with_fake_shell(tmp_path, sink, provider_model="nvidia_nim/test-model")
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, self_review=True))

    result = await run_agent("repoyu GitHub'a pushla", deps)

    assert result.ok is False
    assert provider.calls == 0  # deterministik workflow model çağrısını tamamen atlar
    assert not any(isinstance(event, SelfReviewStarted) for event in sink.events)


def test_echo_git_push_is_not_execution_evidence():
    from fusion_cli.engines.agent.loop import _shell_contains_git_action

    assert not _shell_contains_git_action({"command": "echo git push origin main"}, "push")
    assert _shell_contains_git_action({"command": "cd repo && git push origin main"}, "push")
    assert _shell_contains_git_action({"command": "sudo git -C repo push origin main"}, "push")

"""Oturum ve alt ajanların gerçek sağlayıcı mesajlarında istem sınırları."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.cli.repl.persona_commands import persona_turn
from fusion_cli.core.types import Message
from fusion_cli.engines.agent import loop
from fusion_cli.engines.agent.loop import SYSTEM_PROMPT, run_agent
from fusion_cli.engines.agent.team import Persona, SubTask, run_subagent
from fusion_cli.tools.capabilities import CapabilityRegistry

from .fakes import ScriptedProvider, model_result
from .test_system_prompt_layers import _deps


def _persona(body: str = "Yalnız test sonuçlarını değerlendir.") -> Persona:
    return Persona(name="ozel", title="Özel", avatar="", color="", prompt=body)


async def test_session_body_replaces_core_but_project_context_survives(monkeypatch, tmp_path):
    (tmp_path / "CLAUDE.md").write_text("PROJE_KURALI_123", encoding="utf-8")
    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    persona = persona_turn(_persona())
    await run_agent(
        "Merhaba",
        _deps(tmp_path, "nvidia_nim/ornek-model"),
        system_prompt=getattr(persona, "system_prompt", None),
        extra_system=persona.extra_system,
    )
    messages = provider.seen_messages[0]
    assert _persona().prompt in messages[0].content
    assert SYSTEM_PROMPT not in messages[0].content
    assert "PROJE_KURALI_123" not in messages[0].content
    assert any("PROJE_KURALI_123" in message.content for message in messages[1:])


def test_empty_persona_keeps_default_core():
    assert getattr(persona_turn(_persona("  ")), "system_prompt", None) is None


@pytest.mark.parametrize(
    "name,include_rules", [("ozel", True), ("explore", False), ("plan", False)]
)
async def test_nonfork_child_owns_prompt_and_drops_parent_style(
    monkeypatch, tmp_path, name, include_rules
):
    (tmp_path / "CLAUDE.md").write_text("PROJE_KURALI_123", encoding="utf-8")
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "ozel.md").write_text("---\nname: ozel\ndescription: test\n---\nCOCUK_ISTEMI_123")
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.capabilities = CapabilityRegistry(tmp_path / "ev", tmp_path)
    deps.live_history = lambda: [
        Message("system", "UST_ISTEM_123"),
        Message("user", "UST_GOREV_123"),
    ]
    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    monkeypatch.setattr(loop.output_style, "style_prompt", lambda *args, **kwargs: "UST_STIL_123")
    await run_subagent(deps, SubTask("Merhaba", persona=name), depth=0, run_agent=run_agent)
    messages = provider.seen_messages[0]
    assert SYSTEM_PROMPT not in messages[0].content
    assert "UST_STIL_123" not in messages[0].content
    assert "UST_GOREV_123" not in "\n".join(message.content for message in messages)
    assert (
        "PROJE_KURALI_123" in "\n".join(message.content for message in messages)
    ) == include_rules
    assert str(tmp_path) in messages[0].content


async def test_fork_child_reuses_parent_prompt(monkeypatch, tmp_path):
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.live_history = lambda: [
        Message("system", "UST_ISTEM_123\nUST_STIL_123"),
        Message("user", "UST_GOREV_123"),
    ]
    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    await run_subagent(deps, SubTask("Merhaba", inherit_context=True), depth=0, run_agent=run_agent)
    messages = provider.seen_messages[0]
    assert messages[0].content.startswith("UST_ISTEM_123\nUST_STIL_123")
    assert any(message.content == "UST_GOREV_123" for message in messages)


@pytest.mark.parametrize("fork", [False, True])
async def test_child_user_rules_and_main_auto_memory_are_separate(monkeypatch, tmp_path, fork):
    from fusion_cli.history import memory_files

    home = tmp_path / "ev"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("KULLANICI_KURALI_123")
    (tmp_path / "CLAUDE.md").write_text("PROJE_KURALI_123")
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    deps.home = home
    deps.live_history = lambda: [Message("system", "UST_ISTEM_123")]
    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    monkeypatch.setattr(memory_files, "read_external_memory", lambda *args: "ANA_BELLEK_123")
    await run_subagent(deps, SubTask("Merhaba", inherit_context=fork), depth=0, run_agent=run_agent)
    text = "\n".join(message.content for message in provider.seen_messages[0])
    assert "KULLANICI_KURALI_123" in text
    assert "PROJE_KURALI_123" in text
    assert ("ANA_BELLEK_123" in text) == fork


@pytest.mark.parametrize("child", [False, True])
async def test_replacement_context_note_does_not_own_task_images(monkeypatch, tmp_path, child):
    (tmp_path / "CLAUDE.md").write_text("PROJE_KURALI_123")
    deps = _deps(tmp_path, "openai/gpt-4o")
    deps.config = replace(deps.config, agent=replace(deps.config.agent, tags=("vision",)))
    provider = ScriptedProvider([model_result("Tamam.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    images = ("data:image/png;base64,aGVsbG8=",)
    if child:
        await run_subagent(
            deps, SubTask("Görseli açıkla", images=images), depth=0, run_agent=run_agent
        )
    else:
        await run_agent("Görseli açıkla", deps, system_prompt="ÖZEL_ISTEM", images=images)
    messages = provider.seen_messages[0]
    task = next(
        message for message in messages if message.role == "user" and not message.harness_note
    )
    assert task.content == "Görseli açıkla" and task.images == images
    assert any(
        message.harness_note and "PROJE_KURALI_123" in message.content for message in messages
    )
    assert all(not message.images for message in messages if message.harness_note)


async def test_followup_context_is_single_and_persona_can_be_disabled(monkeypatch, tmp_path):
    (tmp_path / "CLAUDE.md").write_text("PROJE_KURALI_123")
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    provider = ScriptedProvider([model_result("Bir."), model_result("İki."), model_result("Üç.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    first = await run_agent("Merhaba", deps, system_prompt="ÖZEL_ISTEM")
    second = await run_agent("Devam", deps, system_prompt="ÖZEL_ISTEM", history=first.messages)
    await run_agent("Bitir", deps, history=second.messages)
    assert sum("PROJE_KURALI_123" in item.content for item in provider.seen_messages[1]) == 1
    final = provider.seen_messages[2]
    assert SYSTEM_PROMPT in final[0].content and "ÖZEL_ISTEM" not in final[0].content
    assert not any(item.harness_note for item in final)


@pytest.mark.parametrize("with_context", [False, True])
async def test_large_real_fork_preserves_original_task_constraints(
    monkeypatch, tmp_path, with_context
):
    from fusion_cli.engines.agent import team_fork

    (tmp_path / "CLAUDE.md").write_text("PROJE_KURALI_123")
    deps = _deps(tmp_path, "nvidia_nim/ornek-model")
    provider = ScriptedProvider([model_result("Tamam."), model_result("Devralındı.")])
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    original = "ROOT_CONSTRAINT_DO_NOT_TOUCH_DATABASE"
    initial = await run_agent(original, deps, system_prompt="ÖZEL_ISTEM" if with_context else None)
    parent = list(initial.messages)
    for index in range(60):
        parent.extend(
            [
                Message("user", f"Takip {index}: " + "x" * 2000),
                Message("assistant", f"Yanıt {index}: " + "y" * 2000),
            ]
        )
    assert sum(len(message.content) for message in parent) > team_fork.FORK_MAX_CHARS
    assert any(message.content == original for message in parent)
    deps.live_history = lambda: parent
    await run_subagent(deps, SubTask("Merhaba", inherit_context=True), depth=0, run_agent=run_agent)
    messages = provider.seen_messages[-1]
    assert any(message.content == original for message in messages)
    assert any("PROJE_KURALI_123" in message.content for message in messages)
    assert any(message.harness_note and "fork:" in message.content for message in messages)
    assert len(messages) < len(parent)


@pytest.mark.parametrize("notes", [False, True])
def test_main_root_anchor_counts_only_real_user_turns(notes):
    from fusion_cli.engines.agent.history import root_anchor_length

    context = [Message("user", "Proje bağlamı", harness_note=True)] if notes else []
    root = Message("user", "ASIL_GOREV_VE_KISIT")
    history = [
        Message("system", "Sistem"),
        *context,
        root,
        Message("assistant", "İlk yanıt"),
        *context,
        Message("user", "İkinci görev"),
    ]
    anchor = history[: root_anchor_length(history)]
    assert root in anchor
    assert anchor[-1].content != "İkinci görev"
    assert root_anchor_length(history) == len(history) - 1


def test_single_real_task_survives_large_fork_with_leading_context():
    from fusion_cli.engines.agent import team_fork

    root = Message("user", "TEK_GOREV_VE_KISIT")
    messages = [Message("user", "Proje bağlamı", harness_note=True), root]
    messages.extend(Message("assistant", str(index) + "x" * 9000) for index in range(12))
    trimmed = team_fork.fork_history(messages)
    assert root in trimmed
    assert len(trimmed) < len(messages)


async def test_main_compaction_keeps_task_outside_lossy_summary(monkeypatch, tmp_path):
    from fusion_cli.engines.agent import compaction

    context = Message("user", "Proje bağlamı", harness_note=True)
    root = Message("user", "ASIL_GOREV_VE_KALICI_KISIT")
    messages = [Message("system", "ÖZEL_ISTEM"), context, root, Message("assistant", "İlk yanıt")]
    for index in range(40):
        messages.extend([Message("user", f"Takip {index}"), Message("assistant", "x" * 2000)])
    provider = ScriptedProvider([model_result("Kasıtlı eksik, kısa özet.")])
    monkeypatch.setattr(compaction, "build_provider", lambda *args, **kwargs: provider)
    compressed = await compaction.compress(
        messages, config=_deps(tmp_path, "nvidia_nim/ornek-model").config, threshold_chars=60000
    )
    assert len(compressed) < len(messages)
    assert compressed[:3] == [messages[0], context, root]
    assert provider.seen_messages
    assert root.content not in provider.seen_messages[0][0].content

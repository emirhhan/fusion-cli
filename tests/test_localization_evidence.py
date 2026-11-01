"""Gerçek arama kanıtları çağrı kimliği ve kaynak özetiyle taşınır."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.loop import run_agent
from fusion_cli.tools import build_registry

from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
from .test_agent_loop import TAM_CEVAP, _deps, _kur


async def test_search_result_exposes_safe_source_digest(tmp_path):
    text = "def target():\n    return 1\n"
    (tmp_path / "target.py").write_text(text)
    result = await build_registry().execute(
        "search_code", {"pattern": "target"}, ToolContext(tmp_path)
    )
    assert result.structured is not None
    hit = result.structured["localization_candidates"][0]
    assert hit["path"] == "target.py"
    assert hit["source_digest"] == hashlib.sha256(text.encode()).hexdigest()
    assert "evidence_call_id" not in hit


async def test_agent_widens_misleading_same_named_functions_and_uses_real_call_id(
    tmp_path, monkeypatch
):
    (tmp_path / "wrong.py").write_text("def same_name():\n    return 'yanlış'\n")
    (tmp_path / "right.py").write_text("def same_name():\n    return 'doğru hedef'\n")
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        replace(
                            tool_call("search_code", pattern="same_name", path="wrong.py"),
                            id="actual-wrong",
                        )
                    ]
                ),
                model_result(
                    tool_calls=[
                        replace(tool_call("search_code", pattern="doğru hedef"), id="actual-right")
                    ]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, RecordingSink())
    deps.config = replace(
        deps.config,
        runtime=replace(deps.config.runtime, localization_cards=True, project_instructions=False),
    )
    await run_agent("same_name doğru hedefi bul", deps, self_review=False, verify=False)
    initial_card = "\n".join(
        message.content
        for message in provider.seen_messages[1]
        if message.role == "system" and message.content.startswith("KANITLI")
    )
    assert "wrong.py" in initial_card and "actual-wrong" in initial_card
    note = "\n".join(message.content for message in provider.seen_messages[2])
    assert "actual-right" in note and "right.py" in note
    assert deps.tool_context.localization.card.candidates[0].path == "right.py"
    assert deps.tool_context.localization.card.candidates[0].evidence_call_id == "actual-right"


async def test_card_is_top_five_frozen_and_rechecks_source_before_prompt(tmp_path):
    import dataclasses

    import pytest

    from fusion_cli.core.localization import LocalizationCard
    from fusion_cli.engines.agent.localization import record_result, refresh_prompt

    for number in range(9):
        (tmp_path / f"source{number}.py").write_text(f"def target{number}():\n    return 1\n")
    context = ToolContext(tmp_path)
    context.localization.enabled = True
    call = replace(tool_call("search_code", pattern="def target"), id="trusted-executor-id")
    result = await build_registry().execute(call.name, {"pattern": "def target"}, context)
    await record_result(call, result, context)
    assert len(context.localization.card.candidates) == 5
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.localization.card.uncertainty = "iddia"
    assert len(LocalizationCard(context.localization.card.candidates * 3).candidates) == 5
    stale = context.localization.card.candidates[0]
    (tmp_path / stale.path).write_text("def changed():\n    return 2\n")
    messages = []
    await refresh_prompt(messages, context)
    assert stale not in context.localization.card.candidates
    assert stale.source_digest not in messages[0].content
    assert len(messages[0].content) < 8000
    assert "return 1" not in messages[0].content


async def test_explicit_search_path_does_not_scan_other_files(tmp_path):
    (tmp_path / "chosen.py").write_text("def chosen():\n    return 1\n")
    (tmp_path / "other.py").write_text("def chosen():\n    return 2\n")
    result = await build_registry().execute(
        "search_code", {"pattern": "chosen", "path": "chosen.py"}, ToolContext(tmp_path)
    )
    assert [entry["path"] for entry in result.structured["localization_candidates"]] == [
        "chosen.py"
    ]


async def test_plan_task_does_not_embed_refreshable_card(tmp_path):
    from fusion_cli.core.execution_plan import PlanPhase, VerificationCheck, VerificationCheckKind
    from fusion_cli.engines.agent.localization import record_result
    from fusion_cli.engines.agent.plan_context import step_prompt, workspace_block

    from .test_plan_repair import _step

    (tmp_path / "target.py").write_text("def target():\n    return 1\n")
    context = ToolContext(tmp_path)
    context.localization.enabled = True
    result = await build_registry().execute("search_code", {"pattern": "target"}, context)
    await record_result(
        replace(tool_call("search_code", pattern="target"), id="discovery-call"), result, context
    )
    step = replace(
        _step("discovery-id"),
        phase=PlanPhase.DISCOVERY,
        verification_checks=(
            VerificationCheck("criterion-real", VerificationCheckKind.TOOL, "search_code"),
        ),
    )
    prompt = step_prompt(step, {}, workspace=workspace_block(context))
    assert "discovery-id" in prompt
    assert "KANITLI YER BELİRLEME KARTI" not in prompt
    assert "discovery-call" not in prompt
    assert context.localization.card.candidates[0].source_digest not in prompt


async def test_model_only_filename_never_creates_evidence(tmp_path, monkeypatch):
    provider = _kur(
        monkeypatch, ScriptedProvider([model_result("Dosya target.py, çağrı=uydurma.")])
    )
    deps = _deps(tmp_path, RecordingSink())
    deps.config = replace(
        deps.config,
        runtime=replace(deps.config.runtime, localization_cards=True, project_instructions=False),
    )
    await run_agent("Dosyayı tarif et", deps, self_review=False, verify=False)
    assert deps.tool_context.localization.card.candidates == ()
    assert provider.seen_messages


async def test_real_discovery_and_localize_provider_prompts_use_task5_ids(tmp_path, monkeypatch):
    from fusion_cli.core.execution_plan import PlanPhase, VerificationCheck, VerificationCheckKind
    from fusion_cli.engines.agent.plan_context import step_deps, step_prompt, workspace_block
    from fusion_cli.engines.agent.playbook_stage import _AgentStageExecutor
    from fusion_cli.engines.workflow import Stage

    from .test_plan_repair import _step

    (tmp_path / "target.py").write_text("def target():\n    return 1\n")
    deps = _deps(tmp_path, RecordingSink())
    deps = replace(
        deps,
        config=replace(
            deps.config,
            runtime=replace(
                deps.config.runtime, localization_cards=True, project_instructions=False
            ),
        ),
    )
    step = replace(
        _step("task5-discovery"),
        phase=PlanPhase.DISCOVERY,
        verification_checks=(
            VerificationCheck("criterion-task5", VerificationCheckKind.TOOL, "search_code"),
        ),
    )
    scoped = step_deps(deps, step, 5, observe=True)
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        replace(
                            tool_call("search_code", pattern="target", path="target.py"),
                            id="task5-real-call",
                        )
                    ]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    await run_agent(
        step_prompt(step, {}, workspace=workspace_block(scoped.tool_context)),
        scoped,
        depth=1,
        self_review=False,
        verify=False,
    )
    prompt = "\n".join(
        message.content for message in provider.seen_messages[1] if message.role == "system"
    )
    assert "task5-discovery" in prompt and "criterion-task5" in prompt
    assert "task5-real-call" in prompt and "target.py" in prompt
    localize_provider = _kur(monkeypatch, ScriptedProvider([model_result(TAM_CEVAP)]))
    await _AgentStageExecutor("target.py yerini belirle", scoped, run_agent).run(Stage.LOCALIZE, {})
    localize_prompt = "\n".join(message.content for message in localize_provider.seen_messages[0])
    assert "Yer belirleme" in localize_prompt
    assert "task5-discovery" in localize_prompt and "criterion-task5" in localize_prompt
    assert "task5-real-call" in localize_prompt


async def test_actual_agent_rejects_source_changed_between_search_and_card(tmp_path, monkeypatch):
    import hashlib

    from fusion_cli.tools import search

    source = tmp_path / "target.py"
    original = b"def target():\n    return 1\n"
    source.write_bytes(original)
    reader = search.read_scoped_source

    def change_after_snapshot(root, relative, *, max_bytes):
        snapshot = reader(root, relative, max_bytes=max_bytes)
        source.write_text("def changed():\n    return 2\n")
        return snapshot

    monkeypatch.setattr(search, "read_scoped_source", change_after_snapshot)
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        replace(
                            tool_call("search_code", pattern="target", path="target.py"),
                            id="real-stale-call",
                        )
                    ]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, RecordingSink())
    deps = replace(
        deps,
        config=replace(
            deps.config,
            runtime=replace(
                deps.config.runtime, localization_cards=True, project_instructions=False
            ),
        ),
    )
    await run_agent(
        "target.py içindeki target yerini incele", deps, self_review=False, verify=False
    )
    card_prompt = "\n".join(
        message.content for message in provider.seen_messages[1] if message.role == "system"
    )
    assert hashlib.sha256(original).hexdigest() not in card_prompt
    assert deps.tool_context.localization.card.candidates == ()
    assert "Güncel kaynak kanıtı yok" in card_prompt


async def test_explicit_user_path_reaches_only_one_source_in_real_agent(tmp_path, monkeypatch):
    from fusion_cli.tools import search

    (tmp_path / "chosen.py").write_text("def target():\n    return 1\n")
    (tmp_path / "other.py").write_text("def target():\n    return 2\n")
    reader = search.read_scoped_source
    opened = []

    def record_source(root, relative, *, max_bytes):
        opened.append(str(relative))
        return reader(root, relative, max_bytes=max_bytes)

    monkeypatch.setattr(search, "read_scoped_source", record_source)
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[tool_call("search_code", pattern="target", path="chosen.py")]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    deps = _deps(tmp_path, RecordingSink())
    deps = replace(
        deps,
        config=replace(
            deps.config,
            runtime=replace(
                deps.config.runtime, localization_cards=True, project_instructions=False
            ),
        ),
    )
    outcome = await run_agent(
        "chosen.py içindeki target yerini incele", deps, self_review=False, verify=False
    )
    assert outcome.tool_calls_made == 1
    assert opened == ["chosen.py"]
    assert "other.py" not in "\n".join(
        message.content
        for message in provider.seen_messages[1]
        if message.role == "system" and message.content.startswith("KANITLI")
    )


async def test_card_prompt_bounds_escaped_metadata(tmp_path):
    from fusion_cli.engines.agent.localization import card_text, record_result

    for number in range(5):
        directory = tmp_path / str(number)
        for _depth in range(4):
            directory /= "\n" * 180
        directory.mkdir(parents=True)
        (directory / "target.py").write_text("def target():\n    return 1\n")
    context = ToolContext(tmp_path)
    context.localization.enabled = True
    result = await build_registry().execute("search_code", {"pattern": "target"}, context)
    await record_result(
        replace(tool_call("search_code", pattern="target"), id="\n" * 160), result, context
    )
    assert len(card_text(context)) <= 8192


@pytest.mark.parametrize("kind", ["definition", "comment", "docstring"])
async def test_search_card_masks_secret_symbol_in_every_provider_message(
    tmp_path, monkeypatch, kind
):
    marker = "ghp_" + "A" * 36
    source = {
        "definition": "def " + marker + "():\n    return 1\n",
        "comment": "# def " + marker + "\n",
        "docstring": '"""\ndef ' + marker + '\n"""\n',
    }[kind]
    (tmp_path / "example.py").write_text(source)
    deps = _deps(tmp_path, RecordingSink())
    deps = replace(
        deps,
        config=replace(
            deps.config,
            runtime=replace(
                deps.config.runtime,
                localization_cards=True,
                project_instructions=False,
                repo_map_chars=0,
            ),
        ),
    )
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=[
                        replace(
                            tool_call("search_code", pattern="def", path="example.py"),
                            id="search-real-id",
                        )
                    ]
                ),
                model_result(TAM_CEVAP),
            ]
        ),
    )
    await run_agent("example.py tanım konumunu incele", deps, self_review=False, verify=False)
    messages = provider.seen_messages[1]
    assert all(marker not in message.content for message in messages)
    assert any("[gizlendi]" in message.content for message in messages if message.role == "tool")
    candidate = deps.tool_context.localization.card.candidates[0]
    assert candidate.source_digest == hashlib.sha256(source.encode()).hexdigest()
    assert candidate.evidence_call_id == "search-real-id"

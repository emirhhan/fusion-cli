"""Efektif ayar bağlayıcısı yalnız hazır girdilere ve gerçek seçime bakar."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from evals.driver_config import ConfigObserver, install
from evals.engine_proof import ImportedEngineProof

from .fakes import make_config


def observer(receipts):
    proof = ImportedEngineProof(
        123, "/fixture/package", "/fixture/entry", "/fixture", "a" * 64, "b" * 40
    )
    return ConfigObserver(proof, lambda: 123, receipts.append)


async def test_actual_selection_originals_once_requirements_and_result_unchanged():
    config = make_config()
    chosen = replace(config.agent, model="fixture/actual")
    requirements = object()
    calls = []
    receipts = []

    def select(config, task_type, requirements=None):
        calls.append((config, task_type, requirements))
        return chosen

    async def run(task, config, *, task_type="general"):
        return engine.select_agent_spec(config, task_type, requirements=requirements)

    session = SimpleNamespace(run_agent_task=run)
    engine = SimpleNamespace(select_agent_spec=select)
    binding = install(observer(receipts), session, engine)
    assert await session.run_agent_task("task", config, task_type="code") is chosen
    assert calls == [(config, "code", requirements)]
    assert len(receipts) == 1
    assert receipts[0].pid == 123
    assert receipts[0].source_digest == "a" * 64
    assert receipts[0].effective.authentication_status == "unknown"
    binding.close()
    assert session.run_agent_task is run
    assert engine.select_agent_spec is select


async def test_scope_config_mismatch_rejected_before_receipt():
    config = make_config()
    receipts = []
    engine = SimpleNamespace(select_agent_spec=lambda config, task_type: config.agent)

    async def run(task, config, *, task_type="general"):
        return engine.select_agent_spec(replace(config), task_type)

    session = SimpleNamespace(run_agent_task=run)
    binding = install(observer(receipts), session, engine)
    with pytest.raises(ValueError):
        await session.run_agent_task("task", config)
    assert not receipts
    binding.close()


def test_unsupported_api_rejected_without_partial_patch():
    session = SimpleNamespace(run_agent_task=lambda prompt: None)
    original = session.run_agent_task
    engine = SimpleNamespace(select_agent_spec=lambda config, task_type: config.agent)
    with pytest.raises(ValueError):
        install(observer([]), session, engine)
    assert session.run_agent_task is original


def test_receipt_pid_mismatch_rejected():
    proof = ImportedEngineProof(123, "", "", "", "a" * 64, "b" * 40)
    with pytest.raises(ValueError):
        ConfigObserver(proof, lambda: 124, lambda receipt: None)


async def test_changed_config_next_task_and_scope_reset_on_exception():
    config = make_config()
    changed = replace(
        config, runtime=replace(config.runtime, max_tokens=config.runtime.max_tokens + 1)
    )
    receipts = []
    engine = SimpleNamespace(select_agent_spec=lambda config, task_type: config.agent)

    async def run(task, config, *, task_type="general"):
        selected = engine.select_agent_spec(config, task_type)
        if task == "fail":
            raise RuntimeError("fixture")
        return selected

    session = SimpleNamespace(run_agent_task=run)
    binding = install(observer(receipts), session, engine)
    with pytest.raises(RuntimeError):
        await session.run_agent_task("fail", config)
    engine.select_agent_spec(config, "outside")
    assert len(receipts) == 1
    await session.run_agent_task("next", changed)
    assert receipts[0].effective.digest != receipts[1].effective.digest
    binding.close()


async def test_concurrent_task_scopes_do_not_mix_config():
    import asyncio

    first = make_config()
    second = replace(first, agent=replace(first.agent, model="fixture/second"))
    receipts = []
    engine = SimpleNamespace(select_agent_spec=lambda config, task_type: config.agent)

    async def run(task, config, *, task_type="general"):
        await asyncio.sleep(0)
        return engine.select_agent_spec(config, task_type)

    session = SimpleNamespace(run_agent_task=run)
    binding = install(observer(receipts), session, engine)
    results = await asyncio.gather(
        session.run_agent_task("a", first), session.run_agent_task("b", second)
    )
    assert results == [first.agent, second.agent]
    assert len(receipts) == 2
    assert receipts[0].effective.digest != receipts[1].effective.digest
    binding.close()

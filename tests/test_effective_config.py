"""Efektif ayar kanıtı yalnız izinli alanlara bakar, sırları taşımaz."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import ClassVar

import pytest
from evals.effective_config import project_effective

from fusion_cli.core.types import ModelSpec

from .fakes import make_config


def test_same_resolved_config_has_stable_canonical_proof():
    config = make_config()
    first = project_effective(config, config.agent, "code")
    second = project_effective(config, config.agent, "code")
    assert first == second
    assert len(first.digest) == 64
    assert (
        first.authentication_status
        == first.cache_initial_state
        == first.dynamic_context_status
        == "unknown"
    )


def test_config_string_canaries_are_digest_only_and_fallback_order_matters():
    secret = "https://fixture.invalid/?token=private-canary"
    agent = ModelSpec(name=secret, model=secret, fallback=("first", "second"))
    config = replace(make_config(), agent=agent, task_model_map={secret: secret})
    first = project_effective(config, agent, secret)
    assert secret not in repr(first)
    changed = replace(agent, fallback=("second", "first"))
    assert project_effective(config, changed, secret).digest != first.digest


def test_unlisted_secret_properties_are_never_read():
    class Config:
        agent = ModelSpec("a", "fixture/a")
        judge = agent
        candidates = ()
        vision = teacher = None
        task_model_map: ClassVar[dict[str, str]] = {}
        runtime = SimpleNamespace(request_timeout_s=10.0)
        embedding = SimpleNamespace(provider="fixture", model="fixture/embed")

        @property
        def web_sessions(self):
            raise AssertionError("Sır alanına erişildi.")

        @property
        def source(self):
            raise AssertionError("Dosyaya erişildi.")

    proof = project_effective(Config(), Config.agent, "code")
    assert "runtime.model_retry_attempts" in proof.missing_fields
    assert proof.authentication_status == "unknown"


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_tokens", True),
        ("request_timeout_s", float("nan")),
        ("request_timeout_s", float("inf")),
        ("teacherless", "false"),
        ("retry_delays_s", (1, float("nan"))),
    ],
)
def test_invalid_resolved_field_is_rejected(field, value):
    config = make_config()
    broken = replace(config, runtime=replace(config.runtime, **{field: value}))
    with pytest.raises(ValueError):
        project_effective(broken, config.agent, "code")


def test_numeric_budget_and_retry_changes_change_digest():
    config = make_config()
    base = project_effective(config, config.agent, "code")
    runtime = replace(config.runtime, model_retry_attempts=config.runtime.model_retry_attempts + 1)
    assert (
        project_effective(replace(config, runtime=runtime), config.agent, "code").digest
        != base.digest
    )


def test_mapping_order_is_canonical_but_role_order_is_preserved():
    config = make_config()
    first = replace(config, task_model_map={"code": "a", "chat": "b"})
    second = replace(config, task_model_map={"chat": "b", "code": "a"})
    assert project_effective(first, config.agent, "code") == project_effective(
        second, config.agent, "code"
    )
    candidates = (ModelSpec("a", "fixture/a"), ModelSpec("b", "fixture/b"))
    assert (
        project_effective(replace(config, candidates=candidates), config.agent, "code").digest
        != project_effective(
            replace(config, candidates=candidates[::-1]), config.agent, "code"
        ).digest
    )


def test_projector_never_loads_config_files_or_environment(monkeypatch):
    import os
    from pathlib import Path

    from fusion_cli.config import loader

    config = make_config()

    def forbidden(*args, **kwargs):
        raise AssertionError("Saf kanıt dış kaynağa erişti.")

    monkeypatch.setattr(loader, "load_config", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    assert project_effective(config, config.agent, "code").digest


def test_selected_agent_is_separate_from_declared_role():
    config = make_config()
    selected = ModelSpec("mapped", "fixture/mapped")
    declared = project_effective(config, config.agent, "code")
    actual = project_effective(config, selected, "code")
    assert actual.digest != declared.digest
    by_path = {item.path: item for item in actual.fields}
    assert by_path["agent.model"].value != by_path["selected_agent.model"].value


def test_missing_optional_role_differs_from_explicit_absence():
    config = make_config()
    present = project_effective(config, config.agent, "code")
    legacy = SimpleNamespace(
        runtime=config.runtime,
        agent=config.agent,
        judge=config.judge,
        candidates=config.candidates,
        task_model_map=config.task_model_map,
        embedding=config.embedding,
    )
    missing = project_effective(legacy, config.agent, "code")
    assert "teacher" in missing.missing_fields
    assert present.digest != missing.digest


def test_model_text_sequence_types_are_not_silently_coerced():
    config = make_config()
    malformed = replace(config.agent, fallback="fixture/not-a-list")
    with pytest.raises(ValueError):
        project_effective(config, malformed, "code")

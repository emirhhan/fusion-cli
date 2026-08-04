"""EffectContract + deterministik Git push workflow kabul testleri."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fusion_cli.core.events import ToolExecuted
from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.effects.detect import (
    detect_contract,
    extract_branch_reference,
    extract_repository_reference,
)
from fusion_cli.engines.effects.model import EffectKind
from fusion_cli.engines.effects.runner import maybe_run_effect_workflow
from fusion_cli.tools import build_registry

from .fakes import AlwaysApprove, RecordingSink, ScriptedAsker, make_config


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self.sink = sink

    def publish(self, event) -> None:
        self.sink.handle(event)


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=check
    )


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    local = tmp_path / "local"
    remote = tmp_path / "remote.git"
    local.mkdir()
    _git(local, "init", "-b", "main")
    _git(local, "config", "user.name", "Fusion Test")
    _git(local, "config", "user.email", "fusion@example.invalid")
    (local / "README.md").write_text("ilk\n", encoding="utf-8")
    _git(local, "add", "README.md")
    _git(local, "commit", "-m", "initial")
    _git(tmp_path, "init", "--bare", str(remote))
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
    _git(local, "remote", "add", "origin", str(remote))
    _git(local, "push", "-u", "origin", "main")
    return local, remote


def _deps(
    root: Path,
    memory: Path,
    sink: RecordingSink,
    *,
    asker=None,
) -> AgentDeps:
    return AgentDeps(
        config=make_config(memory_dir=memory),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=root),
        asker=asker,
    )


def _remote_head(remote: Path, branch: str = "main") -> str:
    return _git(remote, "rev-parse", f"refs/heads/{branch}").stdout.strip()


def _local_head(local: Path) -> str:
    return _git(local, "rev-parse", "HEAD").stdout.strip()


def test_git_push_contract_and_parameter_extraction():
    contract = detect_contract("emirhhan/fusion_cli reposuna pushla")
    assert contract is not None
    assert contract.kind is EffectKind.GIT_PUSH
    assert contract.deterministic_handler == "git_push"
    assert extract_repository_reference("repo emirhhan/fusion_cli olsun") == "emirhhan/fusion_cli"
    assert extract_branch_reference("main branch'ine pushla") == "main"


async def test_git_push_workflow_commits_pushes_and_verifies(tmp_path):
    local, remote = _repository(tmp_path)
    (local / "README.md").write_text("güncel\n", encoding="utf-8")
    (local / "src.py").write_text("print('ok')\n", encoding="utf-8")
    # Bunlar otomatik commit'e alınmamalı.
    (local / ".env").write_text("SECRET=never\n", encoding="utf-8")
    (local / "debug.log").write_text("noise\n", encoding="utf-8")

    sink = RecordingSink()
    result = await maybe_run_effect_workflow(
        "Mevcut repoyu güncel haliyle pushla",
        _deps(local, tmp_path / "memory", sink),
        build_registry(),
    )

    assert result is not None and result.ok
    assert _local_head(local) == _remote_head(remote)
    assert "Push tamamlandı" in result.final_text
    assert "uzak HEAD doğrulandı" in result.final_text
    assert ".env" not in _git(local, "ls-files").stdout.splitlines()
    assert "debug.log" not in _git(local, "ls-files").stdout.splitlines()
    assert any(isinstance(event, ToolExecuted) for event in sink.events)
    records = list((tmp_path / "memory" / "effect-workflows").glob("*.json"))
    assert len(records) == 1
    assert '"status": "completed"' in records[0].read_text(encoding="utf-8")


async def test_git_push_bypasses_model_and_cannot_end_with_intent_text(
    monkeypatch, tmp_path
):
    local, remote = _repository(tmp_path)
    (local / "README.md").write_text("ikinci\n", encoding="utf-8")
    sink = RecordingSink()
    deps = _deps(local, tmp_path / "memory", sink)

    def _model_must_not_run(*args, **kwargs):
        raise AssertionError("Git push workflow LLM provider çağırmamalı")

    from fusion_cli.engines.agent import loop

    monkeypatch.setattr(loop, "build_provider", _model_must_not_run)
    outcome = await run_agent("Bu repoyu pushla", deps)

    assert outcome.ok
    assert outcome.model_calls_made == 0
    assert _local_head(local) == _remote_head(remote)
    assert "pushluyorum" not in outcome.final_text.lower()


async def test_non_fast_forward_without_exact_confirmation_never_force_pushes(tmp_path):
    local, remote = _repository(tmp_path)
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(remote), str(other))
    _git(other, "config", "user.name", "Other")
    _git(other, "config", "user.email", "other@example.invalid")
    (other / "remote.txt").write_text("uzak\n", encoding="utf-8")
    _git(other, "add", "remote.txt")
    _git(other, "commit", "-m", "remote change")
    _git(other, "push", "origin", "main")
    remote_before = _remote_head(remote)

    (local / "local.txt").write_text("yerel\n", encoding="utf-8")
    asker = ScriptedAsker("hayır")
    result = await maybe_run_effect_workflow(
        "Repoyu pushla; force gerekirse onay iste",
        _deps(local, tmp_path / "memory", RecordingSink(), asker=asker),
        build_registry(),
    )

    assert result is not None and not result.ok
    assert _remote_head(remote) == remote_before
    assert "Push yapılmış kabul edilmemelidir" in result.final_text
    assert any("FORCE-WITH-LEASE ONAYLIYORUM" in q for q in asker.questions)


async def test_exact_force_with_lease_confirmation_pushes_and_verifies(tmp_path):
    local, remote = _repository(tmp_path)
    other = tmp_path / "other"
    _git(tmp_path, "clone", str(remote), str(other))
    _git(other, "config", "user.name", "Other")
    _git(other, "config", "user.email", "other@example.invalid")
    (other / "remote.txt").write_text("uzak\n", encoding="utf-8")
    _git(other, "add", "remote.txt")
    _git(other, "commit", "-m", "remote change")
    _git(other, "push", "origin", "main")

    (local / "local.txt").write_text("yerel\n", encoding="utf-8")
    asker = ScriptedAsker("FORCE-WITH-LEASE ONAYLIYORUM")
    result = await maybe_run_effect_workflow(
        "Repoyu pushla; force gerekirse açık onay iste",
        _deps(local, tmp_path / "memory", RecordingSink(), asker=asker),
        build_registry(),
    )

    assert result is not None and result.ok
    assert _remote_head(remote) == _local_head(local)
    assert any("FORCE-WITH-LEASE ONAYLIYORUM" in q for q in asker.questions)


async def test_temporary_branch_requires_target_confirmation(tmp_path):
    local, remote = _repository(tmp_path)
    _git(local, "checkout", "-b", "repair/test")
    (local / "repair.txt").write_text("repair\n", encoding="utf-8")
    asker = ScriptedAsker("mevcut")

    result = await maybe_run_effect_workflow(
        "Repoyu pushla",
        _deps(local, tmp_path / "memory", RecordingSink(), asker=asker),
        build_registry(),
    )

    assert result is not None and result.ok
    assert _remote_head(remote, "repair/test") == _local_head(local)
    assert any("Hedef branch belirsiz" in q for q in asker.questions)


async def test_rerun_is_idempotent_and_does_not_create_empty_commit(tmp_path):
    local, remote = _repository(tmp_path)
    (local / "README.md").write_text("güncel\n", encoding="utf-8")
    deps = _deps(local, tmp_path / "memory", RecordingSink())

    first = await maybe_run_effect_workflow("Repoyu pushla", deps, build_registry())
    count_after_first = int(_git(local, "rev-list", "--count", "HEAD").stdout.strip())
    second = await maybe_run_effect_workflow("Repoyu pushla", deps, build_registry())
    count_after_second = int(_git(local, "rev-list", "--count", "HEAD").stdout.strip())

    assert first is not None and first.ok
    assert second is not None and second.ok
    assert count_after_second == count_after_first
    assert _remote_head(remote) == _local_head(local)

async def test_push_exit_zero_without_hash_match_is_not_completed(monkeypatch, tmp_path):
    from fusion_cli.engines.effects.git_push import GitPushWorkflow

    local, remote = _repository(tmp_path)
    (local / "README.md").write_text("hash testi\n", encoding="utf-8")
    real_remote_head = GitPushWorkflow._remote_head
    calls = 0

    async def _mismatch_after_push(self, branch: str):
        nonlocal calls
        calls += 1
        actual = await real_remote_head(self, branch)
        return actual if calls == 1 else "0" * 40

    monkeypatch.setattr(GitPushWorkflow, "_remote_head", _mismatch_after_push)
    result = await maybe_run_effect_workflow(
        "Repoyu pushla",
        _deps(local, tmp_path / "memory", RecordingSink()),
        build_registry(),
    )

    assert result is not None and not result.ok
    assert "hashleri eşleşmiyor" in result.final_text
    assert "Push tamamlandı" not in result.final_text
    # Gerçek remote değişmiş olsa bile post-condition sahte/uyuşmaz görünürse başarı yok.
    assert _remote_head(remote) == _local_head(local)


async def test_large_untracked_artifact_is_skipped(tmp_path):
    local, remote = _repository(tmp_path)
    (local / "README.md").write_text("güncel\n", encoding="utf-8")
    (local / "large.bin").write_bytes(b"x" * (10 * 1024 * 1024 + 1))

    result = await maybe_run_effect_workflow(
        "Repoyu pushla",
        _deps(local, tmp_path / "memory", RecordingSink()),
        build_registry(),
    )

    assert result is not None and result.ok
    assert "large.bin" in result.final_text
    assert "large.bin" not in _git(local, "ls-files").stdout.splitlines()
    assert _remote_head(remote) == _local_head(local)

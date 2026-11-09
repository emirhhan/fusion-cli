"""Adım kapısı önbelleği: mutasyonsuz adımda tekrar build yok, final her zaman tam (A4-16)."""

from __future__ import annotations

from dataclasses import dataclass, field

from fusion_cli.core.execution_plan import ExecutionPlan, PlanStep, RetrySafety
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent.gate_cache import GateCache, GateScope, step_mutates, workspace_key
from fusion_cli.engines.agent.lesson_attribution import LessonTurnState
from fusion_cli.engines.agent.loop import AgentOutcome
from fusion_cli.engines.agent.plan_runner import run_execution_plan


class _Publisher:
    def publish(self, event: object) -> None:
        del event


class _SayacliKapi:
    """Çağrı sayısını tutan proje kapısı."""

    def __init__(self, sonuc: VerificationResult | None = None) -> None:
        self.cagri = 0
        self.sonuc = sonuc or VerificationResult(ok=True)

    async def verify(self) -> VerificationResult:
        self.cagri += 1
        return self.sonuc


@dataclass
class _Deps:
    tool_context: ToolContext
    context_step: PlanStep | None = None
    context_plan_id: str | None = None
    lesson_state: LessonTurnState | None = None
    verifier: object | None = None
    execution: object | None = None
    effect_recorder: object | None = None
    budget: object | None = None
    checkpoint_store: object | None = None
    conversation_id: str = ""
    config: object | None = None
    publisher: object = field(default_factory=_Publisher)


def _adim(step_id: str, *, etki: tuple[str, ...] = (), bagimli: tuple[str, ...] = ()) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        goal=f"{step_id} işini yap",
        depends_on=bagimli,
        expected_effects=etki,
        allowed_tool_families=("files",),
        success_criteria=(f"{step_id} kanıtlandı",),
        verification_hint="denetle",
        retry_safety=RetrySafety.SAFE,
    )


async def _koş(tmp_path, adimlar, kapi, yaz):
    deps = _Deps(ToolContext(root=tmp_path), verifier=kapi)

    async def agent(task, turn_deps, **kwargs):
        del kwargs
        ad = next(s.step_id for s in adimlar if f"{s.step_id} işini" in task)
        mutasyon = yaz(ad, tmp_path, turn_deps)
        return AgentOutcome(
            final_text="tamam", messages=[], model_calls_made=1, mutating_tool_calls_made=mutasyon
        )

    plan = ExecutionPlan("p", "iş", tuple(adimlar))
    return await run_execution_plan("iş", deps, agent, plan=plan)


def _yaz_yalniz_ilk(ad, kok, turn_deps):
    if ad != "yaz":
        return 0
    yol = kok / "a.txt"
    yol.write_text("içerik", encoding="utf-8")
    turn_deps.tool_context.touched.add(yol)
    return 1


async def test_salt_okuma_adimlari_gecen_kapiyi_yeniden_kosturmaz(tmp_path):
    """Yazan adım tam kapıyı koşar; ardından gelen iki salt-okuma adımı önbellekten alır."""
    adimlar = [
        _adim("yaz", etki=("file:a.txt",)),
        _adim("oku1", bagimli=("yaz",)),
        _adim("oku2", bagimli=("oku1",)),
    ]
    kapi = _SayacliKapi()

    sonuc = await _koş(tmp_path, adimlar, kapi, _yaz_yalniz_ilk)

    assert sonuc.ok is True
    # taban ölçüm (1) + yazan adım (1) + final kabul (1); iki salt-okuma adımı önbellekten.
    assert kapi.cagri == 3


async def test_mutasyonlu_adim_her_zaman_tam_kapi_kosar(tmp_path):
    adimlar = [
        _adim("a", etki=("workspace_mutation",)),
        _adim("b", etki=("workspace_mutation",), bagimli=("a",)),
    ]
    kapi = _SayacliKapi()

    def yaz(ad, kok, turn_deps):
        yol = kok / f"{ad}.txt"
        yol.write_text(ad, encoding="utf-8")
        turn_deps.tool_context.touched.add(yol)
        return 1

    sonuc = await _koş(tmp_path, adimlar, kapi, yaz)

    assert sonuc.ok is True
    assert kapi.cagri == 4  # taban + iki adım + final


async def test_dokunulan_dosya_degisirse_onbellek_isabet_etmez(tmp_path):
    yol = tmp_path / "a.txt"
    yol.write_text("bir", encoding="utf-8")
    onbellek = GateCache()
    anahtar = workspace_key({yol})
    onbellek.store(anahtar, VerificationResult(ok=True))

    assert onbellek.lookup(anahtar) is not None
    yol.write_text("iki farklı uzunlukta", encoding="utf-8")
    assert onbellek.lookup(workspace_key({yol})) is None


def test_dusen_kapi_onbellege_alinmaz_ve_kaydi_siler():
    onbellek = GateCache()
    onbellek.store("k", VerificationResult(ok=True))
    onbellek.store("k", VerificationResult(ok=False, findings=("kırık",)))

    assert onbellek.lookup("k") is None


def test_kayit_omru_dolunca_isabet_etmez():
    saat = [0.0]
    onbellek = GateCache(ttl_s=10, clock=lambda: saat[0])
    onbellek.store("k", VerificationResult(ok=True))
    saat[0] = 11.0

    assert onbellek.lookup("k") is None


def test_adim_mutasyon_siniflandirmasi():
    assert step_mutates(_adim("a", etki=("file:x.txt",)))
    assert step_mutates(_adim("a", etki=("shell_action",)))
    assert not step_mutates(_adim("a"))
    assert GateScope(GateCache()).outer_touched == frozenset()


async def test_step_cache_rechecks_changed_lock_and_test_configuration(tmp_path):
    """Kaynak sabitken aynı boyut/zamandaki ortam dosyası değişimi kapıyı yeniden koşar."""
    import os
    import shlex
    import sys

    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.engines.agent.verification import CommandVerifier

    class CountingVerifier(CommandVerifier):
        calls = 0

        async def verify(self):
            self.calls += 1
            return await super().verify()

    source = tmp_path / "source.py"
    source.write_text("value = 1\n")
    lock = tmp_path / "uv.lock"
    config = tmp_path / "pytest.ini"
    lock.write_text("one")
    config.write_text("one")
    verifier = CountingVerifier(
        (f"{shlex.quote(sys.executable)} -c 'pass'",), cwd=str(tmp_path), timeout_s=3
    )
    deps = _Deps(ToolContext(root=tmp_path), verifier=verifier)
    deps.tool_context.touched.add(source)
    scope = GateScope(GateCache())
    outcome = AgentOutcome("", [])
    step = _adim("oku")
    await verify_step(step, outcome, deps, gate=scope)
    await verify_step(step, outcome, deps, gate=scope)
    assert verifier.calls == 1
    for path in (lock, config):
        previous = path.stat()
        path.write_text("two")
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        await verify_step(step, outcome, deps, gate=scope)
    assert verifier.calls == 3


async def test_step_cache_rechecks_runtime_command_and_cwd_changes(tmp_path):
    import shlex
    import sys

    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.engines.agent.verification import CommandVerifier

    runtime = ["runner-v1"]

    class CountingVerifier(CommandVerifier):
        calls = 0

        async def verify(self):
            self.calls += 1
            return await super().verify()

    command = f"{shlex.quote(sys.executable)} -c 'pass'"
    verifier = CountingVerifier(
        (command,), cwd=str(tmp_path), timeout_s=3, runtime_identity=lambda: runtime[0]
    )
    deps = _Deps(ToolContext(root=tmp_path), verifier=verifier)
    scope = GateScope(GateCache())
    step, outcome = _adim("oku"), AgentOutcome("", [])
    await verify_step(step, outcome, deps, gate=scope)
    runtime[0] = "runner-v2"
    await verify_step(step, outcome, deps, gate=scope)
    assert verifier.calls == 2
    other = tmp_path / "other"
    other.mkdir()
    for cwd, commands in ((str(other), (command,)), (str(other), (command + " ",))):
        current = CountingVerifier(
            commands, cwd=cwd, timeout_s=3, runtime_identity=lambda: runtime[0]
        )
        deps.verifier = current
        await verify_step(step, outcome, deps, gate=scope)
        assert current.calls == 1


def test_unverified_runner_is_not_cached_as_passing_gate():
    from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
    from fusion_cli.core.execution_plan import VerificationCheckKind

    cache = GateCache()
    result = VerificationResult(
        ok=True,
        evidence=(
            CriterionEvidence(
                "pytest",
                VerificationCheckKind.COMMAND,
                EvidenceStatus.UNVERIFIED,
                "koşucu yok",
                command="pytest",
            ),
        ),
    )
    cache.store("workspace", result)
    assert cache.lookup("workspace") is None


async def test_step_cache_rechecks_runner_content_without_source_changes(tmp_path):
    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.engines.agent.verification import CommandVerifier

    runner = tmp_path / "fixture-runner"
    runner.write_text("#!/bin/sh\nexit 0\n")
    runner.chmod(0o700)
    verifier = CommandVerifier(("./fixture-runner",), cwd=str(tmp_path), timeout_s=3)
    deps = _Deps(ToolContext(root=tmp_path), verifier=verifier)
    scope = GateScope(GateCache())
    await verify_step(_adim("oku"), AgentOutcome("", []), deps, gate=scope)
    runner.write_text("#!/bin/sh\nexit 1\n")
    result = await verify_step(_adim("oku"), AgentOutcome("", []), deps, gate=scope)
    assert not result.ok
    assert result.failure_evidence[0].family == "command_failed"


async def test_build_verifier_hashes_injected_external_runner_at_step_gate(tmp_path):
    from types import SimpleNamespace

    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.engines.agent.verification import build_verifier

    project = tmp_path / "project"
    project.mkdir()
    runner = tmp_path / "external-runner"
    runner.write_text("runner version one")
    config = SimpleNamespace(
        runtime=SimpleNamespace(
            verification_commands=("printf checked",),
            web_verification=False,
            browser_verification=False,
            visual_verification=False,
        )
    )
    verifier = build_verifier(
        config, root=project, tool_context=None, runner_resolver=lambda _program: str(runner)
    )
    deps = _Deps(ToolContext(root=project), verifier=verifier)
    scope = GateScope(GateCache())
    step, outcome = _adim("oku"), AgentOutcome("", [])
    await verify_step(step, outcome, deps, gate=scope)
    await verify_step(step, outcome, deps, gate=scope)
    assert scope.cache.hits == 1
    runner.write_text("runner version two")
    await verify_step(step, outcome, deps, gate=scope)
    assert scope.cache.hits == 1


async def test_step_gate_rechecks_safe_symlink_config_and_lock_targets(tmp_path):
    import shlex
    import sys

    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.engines.agent.verification import CommandVerifier

    settings = tmp_path / "settings"
    settings.mkdir()
    config, lock = settings / "pytest.ini", settings / "uv.lock"
    config.write_text("pass")
    lock.write_text("pass")
    (tmp_path / "pytest.ini").symlink_to("settings/pytest.ini")
    (tmp_path / "uv.lock").symlink_to("settings/uv.lock")
    script = (
        "from pathlib import Path; "
        "assert all(Path(p).read_text()=='pass' for p in ('pytest.ini','uv.lock'))"
    )
    verifier = CommandVerifier(
        (f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}",), cwd=str(tmp_path), timeout_s=3
    )
    deps = _Deps(ToolContext(root=tmp_path), verifier=verifier)
    for target in (config, lock):
        target.write_text("pass")
        scope = GateScope(GateCache())
        assert (await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)).ok
        target.write_text("fail")
        result = await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)
        assert not result.ok
        assert scope.cache.hits == 0
        target.write_text("pass")


async def test_step_gate_rechecks_effective_child_config_and_lock(tmp_path):
    import shlex
    import sys

    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.engines.agent.verification import CommandVerifier

    child = tmp_path / "child"
    child.mkdir()
    config, lock = child / "pytest.ini", child / "uv.lock"
    config.write_text("pass")
    lock.write_text("pass")
    script = (
        "from pathlib import Path; "
        "assert all(Path(p).read_text()=='pass' for p in ('pytest.ini','uv.lock'))"
    )
    verifier = CommandVerifier(
        (f"cd child && {shlex.quote(sys.executable)} -c {shlex.quote(script)}",),
        cwd=str(tmp_path),
        timeout_s=3,
    )
    deps = _Deps(ToolContext(root=tmp_path), verifier=verifier)
    for target in (config, lock):
        scope = GateScope(GateCache())
        assert (await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)).ok
        target.write_text("fail")
        assert not (await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)).ok
        assert scope.cache.hits == 0
        target.write_text("pass")


async def test_unresolved_or_unsafe_environment_disables_step_cache(tmp_path):
    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.engines.agent.verification import CommandVerifier

    project, outside = tmp_path / "project", tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    target = outside / "config.ini"
    target.write_text("fixture")
    for command in ("true && true", "true"):
        config = project / "pytest.ini"
        if command == "true":
            config.symlink_to(target)
        verifier = CommandVerifier((command,), cwd=str(project), timeout_s=3)
        deps = _Deps(ToolContext(root=project), verifier=verifier)
        scope = GateScope(GateCache())
        for _ in range(2):
            assert (await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)).ok
        assert scope.cache.hits == 0


async def test_child_pytest_gate_rechecks_configuration_inherited_from_project_root(tmp_path):
    import shlex
    import sys

    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.engines.agent.verification import CommandVerifier

    child = tmp_path / "child"
    child.mkdir()
    (child / "test_fixture.py").write_text("def test_fixture():\n    assert True\n")
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n")
    command = f"cd child && {shlex.quote(sys.executable)} -m pytest -q"
    verifier = CommandVerifier((command,), cwd=str(tmp_path), timeout_s=10)
    deps = _Deps(ToolContext(root=tmp_path), verifier=verifier)
    scope = GateScope(GateCache())
    first = await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)
    assert first.ok
    assert (await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)).ok
    assert scope.cache.hits == 1
    config.write_text("[pytest]\naddopts = --fusion-fixture-invalid-option\n")
    second = await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)
    assert not second.ok
    assert scope.cache.hits == 1


async def test_child_gate_rechecks_intermediate_ancestor_lock_and_config(tmp_path):
    import shlex
    import sys

    from fusion_cli.engines.agent.step_verification import verify_step
    from fusion_cli.engines.agent.verification import CommandVerifier

    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    config, lock = parent / "pytest.ini", tmp_path / "uv.lock"
    config.write_text("pass")
    lock.write_text("pass")
    script = (
        "from pathlib import Path; "
        "assert all(Path(p).read_text()=='pass' for p in ('../pytest.ini','../../uv.lock'))"
    )
    command = f"cd parent/child && {shlex.quote(sys.executable)} -c {shlex.quote(script)}"
    verifier = CommandVerifier((command,), cwd=str(tmp_path), timeout_s=3)
    deps = _Deps(ToolContext(root=tmp_path), verifier=verifier)
    for target in (config, lock):
        scope = GateScope(GateCache())
        assert (await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)).ok
        assert (await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)).ok
        assert scope.cache.hits == 1
        target.write_text("fail")
        assert not (await verify_step(_adim("read"), AgentOutcome("", []), deps, gate=scope)).ok
        assert scope.cache.hits == 1
        target.write_text("pass")

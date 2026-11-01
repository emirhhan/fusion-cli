"""Öğretmen tavsiyesi doğrulanmış sonuç gelmeden başarı dersi olmaz."""

from __future__ import annotations

import pytest

from fusion_cli.engines.agent.engine_tools import _sync_and_log_teacher_answer
from tests.test_ask_teacher import _deps, _SahteDersBellegi


def test_ogretmen_yaniti_hemen_basari_dersi_olmaz(tmp_path):
    deps = _deps(tmp_path, runtime={"teacher_lesson_sync": True})
    deps.lessons = _SahteDersBellegi()
    written, reason = _sync_and_log_teacher_answer(
        deps, deps.tool_context, question="Ne yapmalıyım?", durum="hata", answer="Dosyayı önce oku."
    )
    assert written is False
    assert deps.lessons.eklenenler == []
    assert "doğrulan" in reason


@pytest.mark.parametrize("stale", [False, True])
async def test_tavsiye_yalniz_ilgili_son_kriterle_terfi_eder(tmp_path, stale):
    from dataclasses import replace

    from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.learning_steps import finish_learning
    from fusion_cli.engines.agent.lesson_attribution import LessonTurnState
    from fusion_cli.engines.agent.loop import AgentOutcome
    from fusion_cli.engines.agent.step_verification import evaluate_file_check
    from fusion_cli.engines.agent.teacher_lessons import bind_advice

    deps = _deps(tmp_path, runtime={"teacher_lesson_sync": True})
    deps.lessons = _SahteDersBellegi()
    path = tmp_path / "app.py"
    path.write_text("önce")
    deps.tool_context.fully_read.add(path)
    check = VerificationCheck("sonuç", VerificationCheckKind.FILE_CONTAINS, "app.py", "sonra")
    failed = replace(
        evaluate_file_check(check, tmp_path),
        check_target=check.target,
        check_expected=check.expected,
    )
    deps.lesson_state = LessonTurnState(verification=VerificationResult(False, evidence=(failed,)))
    binding = bind_advice(deps, "sonuç")
    assert binding is not None
    _sync_and_log_teacher_answer(
        deps,
        deps.tool_context,
        question="app.py",
        durum="hata",
        answer="Kontrolü ekle.",
        binding=binding,
    )
    advice_id = deps.pending_advice[0].advice_id
    path.write_text("sonra")
    deps.lesson_state = LessonTurnState(
        verification=VerificationResult(
            True,
            evidence=(
                replace(
                    evaluate_file_check(check, tmp_path),
                    check_target=check.target,
                    check_expected=check.expected,
                ),
            ),
        )
    )
    if stale:
        path.write_text("bozuldu")
    await finish_learning(AgentOutcome("tamam", []), deps, plan_mode=False)
    assert len(deps.lessons.eklenenler) == (0 if stale else 1)
    if not stale:
        assert advice_id in deps.lessons.eklenenler[0].evidence_refs
    await finish_learning(AgentOutcome("tamam", []), deps, plan_mode=False)
    assert len(deps.lessons.eklenenler) == (0 if stale else 1)


def test_kanit_paketi_bayat_hash_yeniden_okuma_ve_sir_sinirini_korur(tmp_path):
    from fusion_cli.engines.agent.evidence_handoff import BUNDLE_CHAR_LIMIT, compile_handoff
    from fusion_cli.tools.files import _revision_of

    deps = _deps(tmp_path, runtime={"subagent_context_mode": "evidence_bundle"})
    path = tmp_path / "app.py"
    path.write_text("önce")
    deps.tool_context.read_revisions[path] = _revision_of(path)
    path.write_text("sonra")
    bundle = compile_handoff(deps, "Görev\nBearer sentetik12345678901234567890")
    assert "yeniden oku" in bundle and "app.py" in bundle
    assert "sentetik12345678901234567890" not in bundle and len(bundle) <= BUNDLE_CHAR_LIMIT


@pytest.mark.parametrize("read_only", [True, False])
@pytest.mark.parametrize(
    "mode,inherit", [("existing", False), ("existing", True), ("evidence_bundle", True)]
)
async def test_gercek_alt_ajan_girisi_kisitlari_ve_ortak_butceyi_korur(
    tmp_path, mode, inherit, read_only
):
    from dataclasses import replace
    from types import SimpleNamespace

    from fusion_cli.core.types import Message
    from fusion_cli.engines.agent.team import SubTask, run_subagent
    from tests.test_team_fork import _deps as team_deps

    deps = team_deps(tmp_path)
    deps.config = replace(
        deps.config, runtime=replace(deps.config.runtime, subagent_context_mode=mode)
    )
    from fusion_cli.core.budget import TurnBudget

    deps.budget = TurnBudget(deps.clock, 4, 1, 1, 1, 1, 1)
    deps.invocation_budget = object()
    deps.live_history = lambda: [Message("user", "ALAKASIZ GEÇMİŞ")]
    captured = []

    async def run(task, child, **kwargs):
        captured.append((child, kwargs))
        return SimpleNamespace(final_text="ok", ok=True, tool_calls_made=0)

    (tmp_path / "docs").mkdir()
    result = await run_subagent(
        deps,
        SubTask(
            "oku",
            read_only=read_only,
            step_limit=2,
            write_scope=("docs/",),
            inherit_context=inherit,
            tool_cap=frozenset({"read_file"}),
        ),
        depth=0,
        run_agent=run,
    )
    assert result.ok, result.text
    assert len(captured) == 1
    child, kwargs = captured[0]
    assert child.budget is deps.budget and child.invocation_budget is deps.invocation_budget
    assert kwargs["step_limit"] <= 2
    assert "write_file" not in kwargs["allowed_tools"]
    assert "read_file" in kwargs["allowed_tools"]
    assert child.tool_context.write_scope == (() if read_only else (tmp_path / "docs",))
    if mode == "evidence_bundle":
        assert captured[0][1]["history"] is None
        assert "ALAKASIZ" not in captured[0][1]["extra_system"]


@pytest.fixture
def scripted_teacher_runtime(monkeypatch):
    """Yardımcı model ve ağ sınırları da çevrimdışı kalır."""
    import importlib
    import socket

    import litellm

    from tests.test_ask_teacher import _OgretmenSaglayici

    utility = _OgretmenSaglayici(text="TAMAM")
    for name in (
        "narration",
        "learning",
        "liveness",
        "compaction",
        "goal_judge",
        "risk_classifier",
    ):
        module = importlib.import_module("fusion_cli.engines.agent." + name)
        monkeypatch.setattr(module, "build_provider", lambda *args, **kwargs: utility)
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Canlı çağrı yasak")

    async def async_forbidden(*args, **kwargs):
        return forbidden(*args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(litellm, "completion", forbidden)
    monkeypatch.setattr(litellm, "acompletion", async_forbidden)
    yield
    assert not attempts


def _advice_case_verifier(root, case):
    from dataclasses import replace

    from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
    from fusion_cli.core.verification import VerificationResult
    from fusion_cli.engines.agent.step_verification import evaluate_file_check

    guard = VerificationCheck("auth-guard", VerificationCheckKind.FILE_CONTAINS, "auth.py", "GUARD")
    audit = VerificationCheck("auth-log", VerificationCheckKind.FILE_CONTAINS, "auth.py", "LOG")
    docs = VerificationCheck("docs", VerificationCheckKind.FILE_CONTAINS, "README.md", "yeni")
    final_checks = {"unrelated_file": (docs,), "unrelated_criterion": (audit,)}
    measured = []

    class Verifier:
        async def verify(self):
            first = not measured
            checks = (guard, audit) if first else final_checks.get(case, (guard,))
            evidence = tuple(
                replace(
                    evaluate_file_check(item, root),
                    check_target=item.target,
                    check_expected=item.expected,
                )
                for item in checks
            )
            measured.append(evidence)
            return VerificationResult(
                not first, findings=("Yetki denetimi eksik",) if first else (), evidence=evidence
            )

    return Verifier(), measured


def _advice_case_provider(case):
    from tests.fakes import ScriptedProvider, model_result, tool_call

    calls = [
        tool_call("read_file", path="auth.py"),
        tool_call("read_file", path="README.md"),
        tool_call("write_file", path="auth.py", content="hazırlık"),
    ]
    first = [model_result(tool_calls=(call,)) for call in calls] + [
        model_result("İlk değişiklik hazır.")
    ]
    advice = {"question": "auth.py yetki kontrolünü düzelt"}
    if case == "truncated":
        advice["question"] += " ek bağlam" * 1000
    if case != "unbound":
        advice["criterion_id"] = "auth-guard"
    repair = [model_result(tool_calls=(tool_call("ask_teacher", **advice),))]
    if case in {"two_advice", "ambiguous"}:
        repair.append(
            model_result(
                tool_calls=(
                    tool_call(
                        "ask_teacher",
                        question="auth.py LOG kontrolünü düzelt",
                        criterion_id="auth-log" if case == "two_advice" else "auth-guard",
                    ),
                )
            )
        )
    path, content = (
        ("README.md", "yeni")
        if case == "unrelated_file"
        else ("auth.py", "LOG" if case == "unrelated_criterion" else "GUARD")
    )
    repair += [
        model_result(tool_calls=(tool_call("write_file", path=path, content=content),)),
        model_result("Düzeltme hazır."),
    ]
    return ScriptedProvider(first + repair)


@pytest.mark.parametrize(
    "case",
    [
        "unrelated_file",
        "unrelated_criterion",
        "two_advice",
        "linked",
        "unbound",
        "ambiguous",
        "truncated",
    ],
)
async def test_root_ogretmen_tavsiyesi_yalniz_olculen_kriter_bagiyla_terfi_eder(
    tmp_path, monkeypatch, scripted_teacher_runtime, case
):
    from fusion_cli.core.events import TeacherAdviceOutcome
    from fusion_cli.core.types import ModelSpec
    from fusion_cli.engines.agent import loop
    from tests.test_ask_teacher import _ogretmen, _OgretmenSaglayici

    teacher = _OgretmenSaglayici(text="Yetki kriteri için GUARD ekle.")
    _ogretmen(monkeypatch, teacher)
    deps = _deps(
        tmp_path,
        teacher=ModelSpec("teacher", "fake/teacher"),
        runtime={
            "teacher_lesson_sync": True,
            "self_review": False,
            "lessons": False,
            "agent_max_steps": 20,
            "teacher_max_brief_chars": 1000 if case == "truncated" else 25000,
        },
    )
    deps.lessons = _SahteDersBellegi()
    (tmp_path / "auth.py").write_text("eksik")
    (tmp_path / "README.md").write_text("eski")
    deps.verifier, measured = _advice_case_verifier(tmp_path, case)
    provider = _advice_case_provider(case)
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    outcome = await loop.run_agent("Dosyayı düzelt ve doğrula", deps, self_review=False)
    assert outcome.ok, outcome.final_text
    assert len(measured) == 2 and len(teacher.seen) == (
        2 if case in {"two_advice", "ambiguous"} else 1
    )
    expected = case in {"linked", "two_advice"}
    assert len(deps.lessons.eklenenler) == int(expected)
    events = [event for event in deps.publisher.events if isinstance(event, TeacherAdviceOutcome)]
    assert [event.verified for event in events] == (
        [True, False]
        if case == "two_advice"
        else [False, False]
        if case == "ambiguous"
        else [expected]
    )
    if expected:
        assert events[0].advice_id in deps.lessons.eklenenler[0].evidence_refs
        assert "auth-guard" in teacher.seen[0].messages[0].content

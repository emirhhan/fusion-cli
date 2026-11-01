"""Fark denetimi ilgisiz geçmişi göndermez, belirsiz stil yorumuyla onarım açmaz."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.execution_plan import VerificationCheck, VerificationCheckKind
from fusion_cli.core.types import Message, ModelResult
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop, review
from fusion_cli.engines.agent.step_verification import evaluate_file_check
from tests.fakes import ScriptedProvider, make_config, model_result, tool_call
from tests.test_ask_teacher import _deps
from tests.test_evidence_handoff import scripted_teacher_runtime as _scripted_teacher_runtime

scripted_teacher_runtime = _scripted_teacher_runtime


async def test_fark_incelemesi_ilgisiz_gecmisi_dislar(tmp_path, monkeypatch):
    captured = []

    async def ask(prompt, config, publisher):
        captured.append(prompt)
        return ModelResult("judge", "fake", "İsimleri daha güzel yapmalısın.", 1, True)

    monkeypatch.setattr(review, "_ask", ask)
    config = make_config(memory_dir=tmp_path)
    config = replace(config, runtime=replace(config.runtime, review_diff_only=True))
    result = await review.review_turn(
        "iş",
        "bitti",
        [Message("user", "İLGİSİZ GEÇMİŞ")],
        config=config,
        diff="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new",
    )
    assert result in (None, "")
    assert not captured or "İLGİSİZ GEÇMİŞ" not in captured[0]


async def test_somut_fark_bulgusu_tek_cagriyla_donulur(tmp_path, monkeypatch):
    import json

    captured = []
    finding = {
        "path": "app.py",
        "line": 1,
        "reproduction": "pytest test_app",
        "issue": "None girdisi kırılıyor",
    }

    async def ask(prompt, config, publisher):
        captured.append(prompt)
        return ModelResult("judge", "fake", json.dumps(finding), 1, True)

    monkeypatch.setattr(review, "_ask", ask)
    config = make_config(memory_dir=tmp_path, runtime={"review_diff_only": True})
    diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new"
    result = await review.review_turn(
        "iş",
        "bitti",
        [Message("user", "ALAKASIZ")],
        config=config,
        diff=diff,
        failures=("None hatası",),
    )
    assert result and "app.py" in result
    assert len(captured) == 1 and "ALAKASIZ" not in captured[0] and "None hatası" in captured[0]


@pytest.mark.parametrize("judge_times_out", [False, True])
@pytest.mark.parametrize("failed", [False, True])
async def test_root_review_guncel_olcum_kriter_ve_hatalarini_tasir(
    tmp_path, monkeypatch, scripted_teacher_runtime, failed, judge_times_out
):

    deps = _deps(
        tmp_path, runtime={"review_diff_only": True, "self_review": True, "lessons": False}
    )
    provider = ScriptedProvider(
        [
            model_result(tool_calls=(tool_call("write_file", path="app.txt", content="tamam"),)),
            model_result("Dosya üretildi."),
        ]
    )
    monkeypatch.setattr(loop, "build_provider", lambda *args, **kwargs: provider)
    monkeypatch.setattr(loop, "MAX_VERIFY_ROUNDS", 1)
    measured = []

    class Verifier:
        async def verify(self):
            evidence = evaluate_file_check(
                VerificationCheck(
                    "CURRENT_CRITERION",
                    VerificationCheckKind.FILE_CONTAINS,
                    "app.txt",
                    "eksik" if failed else "tamam",
                ),
                tmp_path,
            )
            measured.append(evidence)
            stale = evaluate_file_check(
                VerificationCheck(
                    "STALE_CRITERION", VerificationCheckKind.FILE_CONTAINS, "app.txt", "eski"
                ),
                tmp_path,
            )
            deps.lesson_state.verification = VerificationResult(False, evidence=(stale,))
            return VerificationResult(
                not failed, findings=("CURRENT_ERROR",) if failed else (), evidence=(evidence,)
            )

    deps.verifier = Verifier()
    prompts = []

    async def judge(prompt, config, publisher):
        prompts.append(prompt)
        if judge_times_out:
            raise TimeoutError
        return model_result("TAMAM")

    monkeypatch.setattr(review, "_ask", judge)
    await loop.run_agent("app.txt üret", deps, self_review=True)
    assert measured and len(prompts) == 1
    assert "CURRENT_CRITERION" in prompts[0] and "STALE_CRITERION" not in prompts[0]
    from fusion_cli.core.events import SelfReviewFinished

    finished = [event for event in deps.publisher.events if isinstance(event, SelfReviewFinished)]
    assert len(finished) == 1 and finished[0].completed is (not judge_times_out)
    assert ('"status": "failed"' if failed else '"status": "passed"') in prompts[0]
    if failed:
        assert "CURRENT_ERROR" in prompts[0]

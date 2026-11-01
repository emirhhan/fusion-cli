from __future__ import annotations

import pytest
from evals import agent_runner
from evals.agent_runner import FusionAgentRunner
from evals.runner import EvaluationUnavailableError

from fusion_cli.core.events import ModelCallFinished
from fusion_cli.core.types import ModelResult
from fusion_cli.engines.agent.loop import AgentOutcome
from tests.fakes import make_config


async def test_eval_runner_verifier_baglar_ve_eventlerden_model_cagrisi_sayar(
    monkeypatch,
    tmp_path,
):
    sentinel_verifier = object()
    seen = {}

    def fake_build_verifier(config, *, root, tool_context):
        seen["root"] = root
        seen["tool_context"] = tool_context
        return sentinel_verifier

    async def fake_run_agent(request, deps):
        seen["deps"] = deps

        for index in range(3):
            deps.publisher.publish(
                ModelCallFinished(
                    "agent",
                    ModelResult("agent", "yerel/test", "tamam", 1, True),
                    call_id=f"call{index}",
                    requested_model="yerel/test",
                )
            )

        return AgentOutcome(
            final_text="tamam",
            messages=[],
            # Bilerek yanlış/farklı: eval metriği bunu kullanmamalı.
            model_calls_made=99,
        )

    monkeypatch.setattr(agent_runner, "build_verifier", fake_build_verifier)
    monkeypatch.setattr(agent_runner, "run_agent", fake_run_agent)

    runner = FusionAgentRunner(make_config(memory_dir=tmp_path))

    result = await runner.run("görev", root=tmp_path)

    deps = seen["deps"]

    assert deps.verifier is sentinel_verifier
    assert deps.tool_context is seen["tool_context"]
    assert seen["root"] == tmp_path

    # Review/hakem gibi AgentOutcome dışında kalan çağrılar dahil event gerçeği.
    assert result.model_calls == 3


async def test_eval_runner_saglayici_oturumu_yoksa_olcum_yazmaz(
    monkeypatch,
    tmp_path,
):
    async def fake_run_agent(request, deps):
        return AgentOutcome(
            final_text="authentication: Gemini Web oturumu açık değil veya süresi dolmuş.",
            messages=[],
            ok=False,
            model_calls_made=1,
        )

    monkeypatch.setattr(agent_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(agent_runner, "build_verifier", lambda *args, **kwargs: None)

    runner = FusionAgentRunner(make_config(memory_dir=tmp_path))

    with pytest.raises(EvaluationUnavailableError, match="oturumu"):
        await runner.run("görev", root=tmp_path)


async def test_eval_runner_chrome_profili_aciksa_sifir_basari_raporlamaz(monkeypatch, tmp_path):
    async def fake_run_agent(request, deps):
        return AgentOutcome(
            final_text="web oturumu hatası: Bu Fusion Chrome profili hâlâ açık.",
            messages=[],
            ok=False,
            model_calls_made=0,
        )

    monkeypatch.setattr(agent_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(agent_runner, "build_verifier", lambda *args, **kwargs: None)

    runner = FusionAgentRunner(make_config(memory_dir=tmp_path))

    with pytest.raises(EvaluationUnavailableError, match="Chrome profili"):
        await runner.run("görev", root=tmp_path)


@pytest.mark.parametrize(
    "detail",
    [
        "Seçilen model bu görevle uyumsuz: araç desteği.",
        "Bu görev dosya/sistem değişikliği gerektiriyor ama seçili model bunu yapamıyor: "
        "taklit araç desteği henüz eval eşiğinden geçmedi: mutation'a giremez.",
    ],
)
async def test_eval_runner_arac_olcumu_olmayan_modeli_basarisiz_gorev_saymaz(
    monkeypatch, tmp_path, detail
):
    async def fake_run_agent(request, deps):
        return AgentOutcome(
            final_text=detail,
            messages=[],
            ok=False,
            model_calls_made=0,
        )

    monkeypatch.setattr(agent_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(agent_runner, "build_verifier", lambda *args, **kwargs: None)
    runner = FusionAgentRunner(make_config(memory_dir=tmp_path))

    with pytest.raises(EvaluationUnavailableError, match="hiç çalışmadı"):
        await runner.run("görev", root=tmp_path)


async def test_eval_runner_saglayici_asiri_yuklenmesini_basarisiz_gorev_saymaz(
    monkeypatch, tmp_path
):
    async def fake_run_agent(request, deps):
        return AgentOutcome(
            final_text="APIConnectionError: Service temporarily overloaded",
            messages=[],
            ok=False,
            model_calls_made=2,
        )

    monkeypatch.setattr(agent_runner, "run_agent", fake_run_agent)
    monkeypatch.setattr(agent_runner, "build_verifier", lambda *args, **kwargs: None)
    runner = FusionAgentRunner(make_config(memory_dir=tmp_path))

    with pytest.raises(EvaluationUnavailableError, match="aşırı yüklü"):
        await runner.run("görev", root=tmp_path)


def test_eval_model_identity_and_unknown_usage_are_observed_not_assumed():
    from evals.agent_runner import _CountingPublisher, _NullPublisher

    from fusion_cli.core.events import ModelCallFinished
    from fusion_cli.core.types import ModelResult, TokenUsage

    publisher = _CountingPublisher(_NullPublisher())
    publisher.publish(
        ModelCallFinished(
            role="teacher",
            call_id="call1",
            requested_model="local/small",
            result=ModelResult(
                "teacher", "local/small", "tamam", 1, True, served_by="remote/strong"
            ),
        )
    )
    publisher.publish(
        ModelCallFinished(
            role="agent",
            call_id="call2",
            requested_model="local/small",
            result=ModelResult(
                "agent",
                "local/small",
                "tamam",
                1,
                True,
                usage=TokenUsage(prompt_tokens=0, prompt_measured=True),
            ),
        )
    )
    first, second = publisher.calls
    assert first.requested_model == "local/small"
    assert first.served_model == "remote/strong"
    assert first.role == "teacher"
    assert first.prompt_tokens is None
    assert first.cost_usd is None
    assert second.served_model is None
    assert second.prompt_tokens == 0
    assert second.completion_tokens is None


def test_abandoned_call_retains_unknown_usage_and_distinguishes_timeout():
    from evals.agent_runner import _CountingPublisher, _NullPublisher

    from fusion_cli.core.events import ModelCallAbandoned

    publisher = _CountingPublisher(_NullPublisher())
    publisher.publish(
        ModelCallAbandoned(
            call_id="cancelled",
            role="judge",
            model="local/small",
            reason="iptal edildi",
        )
    )
    publisher.publish(
        ModelCallAbandoned(
            call_id="timeout",
            role="agent",
            model="local/small",
            reason="timeout",
        )
    )
    assert publisher.model_calls == 2
    assert publisher.calls[0].outcome == "abandoned"
    assert publisher.calls[1].outcome == "timeout"
    assert publisher.calls[0].prompt_tokens is None
    assert publisher.calls[0].cost_usd is None


async def test_strict_eval_real_runner_cannot_hand_off_to_apprentice(monkeypatch, tmp_path):
    from evals.profiles import EvalProfile, build_runner, prepare_eval_config

    from fusion_cli.engines.agent import loop

    from .test_apprentice_handoff import _deps

    deps, _sink = _deps(tmp_path)
    config = prepare_eval_config(deps.config)
    requested = config.agent.model
    used = []

    def no_provider(spec, **kwargs):
        used.append(spec.model)
        raise AssertionError("Yetersiz yetenekte sağlayıcı çağrılmamalı")

    monkeypatch.setattr(loop, "build_provider", no_provider)
    for profile in (EvalProfile.FUSION_FULL, EvalProfile.FUSION_MINIMAL):
        runner = build_runner(profile, config)
        with pytest.raises(EvaluationUnavailableError, match=r"ölçüm|Ölçüm"):
            await runner.run(
                "ayakkabisite adlı klasör oluştur ve içine index.html yaz", root=tmp_path
            )
        assert runner._config.agent.model == requested
        assert deps.config.tiers
    assert used == []

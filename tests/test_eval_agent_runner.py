from __future__ import annotations

from evals import agent_runner
from evals.agent_runner import FusionAgentRunner

from fusion_cli.engines.agent.loop import AgentOutcome


async def test_eval_runner_verifier_baglar_ve_eventlerden_model_cagrisi_sayar(
    monkeypatch,
    tmp_path,
):
    sentinel_verifier = object()
    seen = {}

    class _Finished:
        pass

    def fake_build_verifier(config, *, root, tool_context):
        seen["root"] = root
        seen["tool_context"] = tool_context
        return sentinel_verifier

    async def fake_run_agent(request, deps):
        seen["deps"] = deps

        deps.publisher.publish(_Finished())
        deps.publisher.publish(_Finished())
        deps.publisher.publish(_Finished())

        return AgentOutcome(
            final_text="tamam",
            messages=[],
            # Bilerek yanlış/farklı: eval metriği bunu kullanmamalı.
            model_calls_made=99,
        )

    monkeypatch.setattr(agent_runner, "ModelCallFinished", _Finished)
    monkeypatch.setattr(agent_runner, "build_verifier", fake_build_verifier)
    monkeypatch.setattr(agent_runner, "run_agent", fake_run_agent)

    runner = object.__new__(FusionAgentRunner)
    runner._config = object()

    result = await runner.run("görev", root=tmp_path)

    deps = seen["deps"]

    assert deps.verifier is sentinel_verifier
    assert deps.tool_context is seen["tool_context"]
    assert seen["root"] == tmp_path

    # Review/hakem gibi AgentOutcome dışında kalan çağrılar dahil event gerçeği.
    assert result.model_calls == 3

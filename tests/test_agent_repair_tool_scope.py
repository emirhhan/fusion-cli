"""Internal corrections retain the original offered and executable tool ceiling."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus
from fusion_cli.core.execution_plan import VerificationCheckKind
from fusion_cli.core.tools import Tool, ToolResult
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop
from fusion_cli.mcp_bridge.discovery import McpDiscovery
from fusion_cli.tools import ToolRegistry

from .fakes import ScriptedProvider, model_result, tool_call
from .test_agent_external_deadline import deps_for


@pytest.mark.parametrize(
    "correction",
    [
        "self_review",
        "verification",
        "verification-fallback",
        "verification-escalated",
        "verification-fallback-retry",
    ],
)
@pytest.mark.parametrize("discovery", [False, True], ids=["static", "lazy-mcp"])
@pytest.mark.parametrize(
    ("allowed", "denied", "expected_allowed", "expected_forbidden"),
    [
        ({"scope_allowed"}, frozenset(), True, False),
        (set(), frozenset(), False, False),
        (None, frozenset(), True, True),
        (None, frozenset({"scope_forbidden"}), True, False),
    ],
    ids=["explicit-cap", "empty-cap", "unrestricted", "inherited-deny"],
)
async def test_repeated_corrections_keep_tool_schema_and_execution_scope(
    tmp_path,
    monkeypatch,
    correction,
    discovery,
    allowed,
    denied,
    expected_allowed,
    expected_forbidden,
):
    # Dropping allowed_tools at either recursive repair call must fail this test:
    # the model deliberately requests an unoffered real tool in both corrections.
    deps = deps_for(tmp_path, None)
    if "fallback" in correction:
        deps.config = replace(
            deps.config, agent=replace(deps.config.agent, fallback=("sahte/corrector",))
        )
    deps.denied_tools = denied
    executed = []
    registry = ToolRegistry()
    for name in ("scope_allowed", "scope_forbidden"):

        async def run(args, context, *, tool_name=name):
            executed.append(tool_name)
            return ToolResult(output="Observed value: available.")

        registry.register(Tool(name, name, {"type": "object", "properties": {}}, run))
    deps.base_registry = registry
    if discovery:
        # Real lazy admission/surface binding, with no configured remote servers.
        deps.mcp_discovery = McpDiscovery(lambda: deps.config, root=tmp_path)

    answer = "The available observations have been summarized in this response."
    results = [model_result(answer)]
    for _ in range(2):
        if correction == "verification-fallback-retry":
            results.append(model_result(ok=False, error="Service temporarily overloaded"))
        results.extend(
            [
                model_result(tool_calls=[tool_call("scope_allowed"), tool_call("scope_forbidden")]),
                model_result(answer),
            ]
        )
    provider = ScriptedProvider(results)
    monkeypatch.setattr(loop, "build_provider", lambda *a, **k: provider)

    async def feedback(*args, **kwargs):
        return "Correct the explanation using only the originally permitted observations."

    monkeypatch.setattr(loop.review, "review_turn", feedback)
    outcome = await loop.run_agent(
        "Summarize the available observations.",
        deps,
        allowed_tools=allowed,
        self_review=False,
        verify=False,
    )
    finding = "The explanation contains an unsupported detail."
    verification = VerificationResult(
        ok=False,
        summary=finding,
        findings=(finding,),
        evidence=(
            CriterionEvidence(
                "research_grounding",
                VerificationCheckKind.TOOL,
                EvidenceStatus.FAILED,
                finding,
            ),
        ),
    )
    for _ in range(2):
        if correction == "self_review":
            outcome = await loop._self_review("Summarize observations.", outcome, deps)
        else:
            escalated = replace(deps) if correction == "verification-escalated" else None
            outcome = await loop._fix_findings(
                verification,
                outcome,
                deps,
                escalation_deps=escalated,
            )

    assert provider.calls == (7 if correction == "verification-fallback-retry" else 5)
    assert Counter(executed) == Counter(
        {
            "scope_allowed": 2 if expected_allowed else 0,
            "scope_forbidden": 2 if expected_forbidden else 0,
        }
    )
    for offered in provider.seen_requests:
        names = {item["function"]["name"] for item in offered}
        assert ("scope_allowed" in names) is expected_allowed
        assert ("scope_forbidden" in names) is expected_forbidden
    assert deps.denied_tools == denied

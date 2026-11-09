"""Protocol controls only: semantic correctness requires the retained live cases."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from fusion_cli.engines.agent import research_grounding as grounding

from .fakes import RecordingSink, model_result
from .test_agent_loop import _deps
from .test_research_grounding import target_sources


@pytest.mark.parametrize(
    ("text", "kind", "expected"),
    [
        ("The legacy endpoint is disabled.", "supported", "supported"),
        ("Eski uç nokta devre dışıdır.", "supported", "supported"),
        ("The legacy endpoint remains enabled.", "contradicted", "issues"),
        ("The endpoint was deprecated exactly one year before removal.", "unsupported", "issues"),
    ],
)
async def test_exact_propositions_reach_judge_without_rewriting_or_lexical_override(
    tmp_path, text, kind, expected
):
    context, target, sources = target_sources(tmp_path, text)
    receipt = replace(sources[0].receipt, text="The legacy endpoint is deprecated and disabled.")
    contract = context.delivery_contract.for_owner(context.root, context.job_scope)
    assert contract is not None
    sources = (grounding.capture_source(receipt, contract, "read-fixture"),)
    deps = _deps(tmp_path, RecordingSink())

    async def judge(prompt):
        payload = json.loads(prompt.split("\nDATA\n", 1)[1])
        assert "".join(span["text"] for span in payload["target"].values()) == text
        assert receipt.text in payload["sources"][0]["spans"].values()
        return model_result(
            json.dumps(
                {
                    "target_digest": payload["target_digest"],
                    "source_digest": payload["source_digest"],
                    "claims": [
                        {
                            "targets": list(payload["target"]),
                            "kind": kind,
                            "sources": [] if kind == "unsupported" else ["s1:1"],
                            "basis": "Fixture decision; no model semantics asserted by this test.",
                        }
                    ],
                }
            )
        )

    verdict = await grounding.review_grounding(target, sources, deps, judge=judge)
    assert verdict.status == expected

"""Sürüm/tarih rakamları açık sıra kanıtının yerini tutamaz."""

from __future__ import annotations

import json

import pytest

from fusion_cli.engines.agent.research_grounding import parse_verdict, request_payload

from .test_research_grounding import target_sources


@pytest.mark.parametrize(
    ("target_text", "source_text"),
    [
        ("This is the third maintenance release.", "Releases: 8.4.0, 8.4.1, 8.4.2."),
        ("Bu üçüncü bakım sürümüdür.", "Releases: 8.4.0, 8.4.1, 8.4.2."),
        ("This is the 3rd maintenance release.", "This is the second maintenance release."),
        ("Bu on birinci bakım sürümüdür.", "This is the first maintenance release."),
    ],
)
def test_supported_label_cannot_bless_ordinal_without_explicit_cited_ordinal(
    tmp_path, target_text, source_text
):
    verdict = _review(tmp_path, target_text, source_text)
    assert verdict.status == "issues"
    assert verdict.claims[0].kind == "unsupported"
    assert "açık sıra" in verdict.claims[0].basis


@pytest.mark.parametrize(
    ("target_text", "source_text"),
    [
        ("Bu ikinci bakım sürümüdür.", "This is the second maintenance release."),
        ("This is the 21st update.", "This is the twenty-first update."),
        ("Bu yirmi birinci güncellemedir.", "This is the 21st update."),
        ("Orion 8.4.2 released 2031-10-25.", "Orion 8.4.2 released 2031-10-25."),
        ("Yayın tarihi 25. Ekim 2031.", "Release date: Oct. 25, 2031."),
        ("Released on October 25th, 2031.", "Release date: 2031-10-25."),
        ("Released Sept. 25th, 2031.", "Release date: 2031-09-25."),
        ("Released September the 25th, 2031.", "Release date: 2031-09-25."),
        ("It completes in one second.", "Duration: 1 s."),
        ("This takes 0.5-second intervals.", "Duration: 0.5 s."),
        ("Use two-second intervals.", "Duration: 2 s."),
        ("Use eleven-second intervals.", "Interval: 11 s."),
        ("Use a thirty-second timeout.", "Timeout: 30 s."),
        ("Use thirty-second intervals.", "Interval: 30 s."),
        (
            "The client provides first-class support for streaming.",
            "The client natively supports streaming.",
        ),
        ("Use first-party support.", "Use official vendor support."),
        ("This is a second-hand device.", "This is a used device."),
        ("This is the 101st update.", "This is the one hundred first update."),
    ],
)
def test_explicit_translated_ordinal_passes_and_date_version_unit_never_becomes_ordinal(
    tmp_path, target_text, source_text
):
    assert _review(tmp_path, target_text, source_text).status == "supported"


def test_matching_ordinal_never_overrides_a_semantic_issue(tmp_path):
    verdict = _review(
        tmp_path,
        "This is the second maintenance release.",
        "The second paragraph describes a different release.",
        kind="unsupported",
    )
    assert verdict.status == "issues"
    assert verdict.claims[0].basis == "The cited ordinal describes an unrelated paragraph."


@pytest.mark.parametrize("duplicate_at", ["root", "claim"])
def test_ambiguous_duplicate_json_keys_cannot_overwrite_a_verdict(tmp_path, duplicate_at):
    assert (
        _review(
            tmp_path,
            "Orion was released October 25.",
            "Orion was released October 25.",
            duplicate_at=duplicate_at,
        ).status
        == "incomplete"
    )


@pytest.mark.parametrize("kind", ["nonfactual", "uncertain"])
async def test_ordinal_in_navigation_or_explicit_uncertainty_reaches_semantic_review(
    tmp_path, kind
):
    from dataclasses import asdict, replace

    from fusion_cli.engines.agent.research_grounding import _digest, review_grounding

    from .fakes import RecordingSink, model_result
    from .test_agent_loop import _deps

    text = (
        "<nav>First | Second</nav>"
        if kind == "nonfactual"
        else "The source does not establish whether this is the third maintenance release."
    )
    _, target, sources = target_sources(tmp_path, text)
    receipt = replace(sources[0].receipt, text="Releases: 8.4.0, 8.4.1, 8.4.2.")
    sources = (replace(sources[0], receipt=receipt, digest=_digest(asdict(receipt))),)
    deps = _deps(tmp_path, RecordingSink())
    called = []

    async def judge(prompt):
        called.append(True)
        payload = json.loads(prompt.split("\nDATA\n", 1)[1])
        return model_result(
            json.dumps(
                {
                    "target_digest": target.digest,
                    "source_digest": payload["source_digest"],
                    "claims": [
                        {
                            "targets": list(payload["target"]),
                            "kind": kind,
                            "sources": [],
                            "basis": "Navigation or explicit source-honest uncertainty.",
                        }
                    ],
                }
            )
        )

    verdict = await review_grounding(target, sources, deps, judge=judge)
    assert called
    assert verdict.status == "supported"
    assert verdict.claims[0].kind == kind


def _review(tmp_path, target_text, source_text, *, kind="supported", duplicate_at=None):
    from dataclasses import asdict, replace

    from fusion_cli.engines.agent.research_grounding import _digest

    _, target, sources = target_sources(tmp_path, target_text)
    receipt = replace(sources[0].receipt, text=source_text)
    sources = (replace(sources[0], receipt=receipt, digest=_digest(asdict(receipt))),)
    payload = request_payload(target, sources)
    text = json.dumps(
        {
            "target_digest": target.digest,
            "source_digest": payload["source_digest"],
            "claims": [
                {
                    "targets": list(payload["target"]),
                    "sources": list(payload["sources"][0]["spans"]),
                    "basis": "The cited ordinal describes an unrelated paragraph.",
                    "kind": kind,
                }
            ],
        }
    )
    if duplicate_at == "root":
        text = text.replace('"claims":', '"claims": [], "claims":', 1)
    elif duplicate_at == "claim":
        text = text.replace('"kind": "supported"', '"kind": "unsupported", "kind": "supported"', 1)
    return parse_verdict(text, target, sources)

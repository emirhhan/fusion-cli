"""Dar metinsel kanıt kontrolü yoğun girdide UI'yi saniyelerce bloke etmez."""

from __future__ import annotations

from time import perf_counter

import pytest

from fusion_cli.engines.agent.technical_evidence import unbacked_technical_literals


@pytest.mark.parametrize(
    "target",
    [
        "`erase_item` " * 4000,
        "<code>" * 8000 + "`erase_item`",
        "<script>" * 6000 + "`erase_item`",
    ],
    ids=["dense-inline", "unclosed-code-tags", "unclosed-script-tags"],
)
def test_dense_or_unclosed_markup_has_bounded_cost_without_dropping_last_claim(target):
    started = perf_counter()
    missing = unbacked_technical_literals(target, ("Module overview.",))
    elapsed = perf_counter() - started

    assert missing == ("erase_item",)
    # Eski yol aynı <=52k karakterde 1.2–4.4 saniye sürüyordu; geniş toleranslı bütçe.
    assert elapsed < 0.75, f"Dar kanıt kontrolü {elapsed:.3f} saniye bloke etti"


def test_integrated_target_snapshot_and_verdict_do_not_rescan_unclosed_script_suffixes(tmp_path):
    from .test_technical_evidence import _review

    target = "<script>" * 6000 + "`erase_item`"
    started = perf_counter()
    verdict = _review(tmp_path, target, "Module contents.")
    elapsed = perf_counter() - started

    assert verdict.status == "issues"
    assert "erase_item" in verdict.claims[0].basis
    assert elapsed < 0.75, f"Entegre kaynak kapısı {elapsed:.3f} saniye bloke etti"


def test_unique_names_keep_bounded_actionable_feedback_and_exact_omitted_count(tmp_path):
    import json
    import re
    from dataclasses import replace

    from fusion_cli.core.research_grounding import TextSpan
    from fusion_cli.engines.agent.research_grounding import _digest, parse_verdict, request_payload

    from .test_research_grounding import target_sources

    _, target, sources = target_sources(tmp_path, "Technical API list.")
    text = " ".join(f"`erase_item_{index}`" for index in range(2500))
    target = replace(
        target, spans=(TextSpan("answer:1", 0, len(text), text, "answer"),), digest=_digest(text)
    )
    payload = request_payload(target, sources)
    raw = {
        "target_digest": target.digest,
        "source_digest": payload["source_digest"],
        "claims": [
            {
                "targets": ["answer:1"],
                "sources": ["s1:1"],
                "kind": "supported",
                "basis": "All listed names are supported.",
            }
        ],
    }
    started = perf_counter()
    verdict = parse_verdict(json.dumps(raw), target, sources)
    elapsed = perf_counter() - started

    assert verdict.status == "issues"
    feedback = verdict.claims[0].basis
    assert len(feedback) <= 600
    assert "erase_item_0" in feedback
    shown = len(re.findall(r"erase_item_\d+", feedback))
    omitted = re.search(r"(\d+) ad daha", feedback)
    assert omitted is not None and int(omitted[1]) == 2500 - shown
    assert elapsed < 0.75, f"Benzersiz ad denetimi {elapsed:.3f} saniye bloke etti"


def test_long_source_whitespace_does_not_create_a_quadratic_normalization_path():
    source = "Module " + " " * 20000 + "overview."
    started = perf_counter()
    missing = unbacked_technical_literals("`erase_item` changed.", (source,))
    elapsed = perf_counter() - started

    assert missing == ("erase_item",)
    assert elapsed < 0.75, f"Kaynak boşluk normalizasyonu {elapsed:.3f} saniye bloke etti"

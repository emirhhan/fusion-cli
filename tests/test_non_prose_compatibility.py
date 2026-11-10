"""Dar doğrusal tarama eski regex'in maske/boşluk ve bölüm kimliklerini korur."""

from __future__ import annotations

import random
import re
from time import perf_counter

import pytest

from fusion_cli.engines.agent.technical_markup import non_prose_text

LEGACY = re.compile(
    r"<!--[\s\S]*?-->|<(?P<opaque>style|script)\b[^>]*>[\s\S]*?</(?P=opaque)\s*>|"
    r"""<(?:"[^"]*"|'[^']*'|[^'">])*>""",
    re.I,
)
CASES = [
    "plain text",
    "<script>`erase_item`</script>after",
    "<script>unclosed",
    "<script><script>inner</script>after</script>",
    "<style>inner</style>after",
    "<code>name</code>",
    "<code>unclosed",
    "<!-- hidden -->visible",
    "<!-- unclosed",
    '<p title="quoted >">visible</p>',
    '<script data=">">inner</script>',
    '<script data="> </script> remainder">visible</script>',
    "<script data='</script>'>inner</script>",
    "<style-variant>inner</style>",
    '<tag quote="unclosed <code>name</code>',
    "a < b > c",
    "<>",
]


@pytest.mark.parametrize("preserve_offsets", [False, True])
@pytest.mark.parametrize("text", CASES)
def test_legacy_closed_unclosed_nested_comment_and_quote_quirks_are_preserved(
    text, preserve_offsets
):
    replacement = (lambda match: " " * len(match.group())) if preserve_offsets else " "

    assert non_prose_text(text, preserve_offsets=preserve_offsets) == LEGACY.sub(replacement, text)


def test_small_generated_cases_keep_both_substitution_forms_identical():
    generator = random.Random(937)
    tokens = [*CASES, "'", '"', "<script", "</STYLE >", "\n", "<!--", "-->"]
    for _ in range(500):
        text = "".join(generator.choices(tokens, k=5))
        assert non_prose_text(text) == LEGACY.sub(" ", text)
        assert non_prose_text(text, preserve_offsets=True) == LEGACY.sub(
            lambda match: " " * len(match.group()), text
        )


def test_unclosed_script_scanning_remains_bounded_and_keeps_following_claim():
    text = "<script>" * 6000 + "`erase_item`"
    started = perf_counter()
    prose = non_prose_text(text, preserve_offsets=True)
    elapsed = perf_counter() - started

    assert prose.endswith("`erase_item`")
    assert len(prose) == len(text)
    assert elapsed < 0.75, f"Düz yazı maskesi {elapsed:.3f} saniye bloke etti"


def _legacy_target_spans(text, prefix):
    from fusion_cli.core.research_grounding import TextSpan
    from fusion_cli.engines.agent.research_grounding import _SENTENCE_END, _spans

    prose = LEGACY.sub(lambda match: " " * len(match.group()), text)
    ends = tuple(match.end() for match in _SENTENCE_END.finditer(prose))
    spans = []
    for block in _spans(text, prefix, prefix):
        start = block.start
        for end in ends:
            if (
                start < end < block.end
                and prose[start:end].strip()
                and prose[end : block.end].strip()
            ):
                spans.append(
                    TextSpan(f"{prefix}:{len(spans) + 1}", start, end, text[start:end], prefix)
                )
                start = end
        spans.append(
            TextSpan(
                f"{prefix}:{len(spans) + 1}", start, block.end, text[start : block.end], prefix
            )
        )
    return tuple(spans)


@pytest.mark.parametrize(
    "fixture_name", ["captured_false_clean.json", "captured_supported_53.json"]
)
def test_actual_captured_target_ids_offsets_and_digest_stay_equal_to_legacy(fixture_name):
    import json
    from dataclasses import asdict
    from pathlib import Path

    from fusion_cli.engines.agent.research_grounding import _digest, _target_spans

    fixture = json.loads(
        (Path(__file__).parent / "fixtures/technical_evidence" / fixture_name).read_text()
    )
    groups = {}
    for key, text in fixture["targets"].items():
        groups.setdefault(key.split(":")[0], []).append(text)
    actual, expected = [], []
    for prefix, parts in groups.items():
        text = "".join(parts)
        actual.extend(_target_spans(text, prefix, prefix))
        expected.extend(_legacy_target_spans(text, prefix))

    assert actual == expected
    assert [span.id for span in actual] == list(fixture["targets"])
    assert _digest([asdict(span) for span in actual]) == _digest(
        [asdict(span) for span in expected]
    )

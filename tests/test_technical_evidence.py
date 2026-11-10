"""Destek etiketi, atıf verilen parçaların içermediği teknik adı aklayamaz."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from fusion_cli.core.research_grounding import (
    ResearchTarget,
    SourceReceipt,
    SourceSnapshot,
    TextSpan,
)
from fusion_cli.engines.agent.research_grounding import _digest, parse_verdict, request_payload

from .test_research_grounding import target_sources

FIXTURES = Path(__file__).parent / "fixtures" / "technical_evidence"


def _fixture_source_text(row):
    parts = []
    for part in row["parts"]:
        if isinstance(part, str):
            parts.append(part)
        else:
            chars = [" "] * part["omitted_chars"]
            for position in part["newlines"]:
                chars[position] = "\n"
            parts.append("".join(chars))
    return "".join(parts)


def _fixture_verdict(tmp_path: Path, name: str):
    fixture = json.loads((FIXTURES / name).read_text())
    spans = tuple(
        TextSpan(key, 0, len(text), text, "answer") for key, text in fixture["targets"].items()
    )
    target = ResearchTarget(
        "accepted-fixture",
        str(tmp_path),
        "fixture-owner",
        "Kaynaklı teknik rapor",
        spans,
        _digest({span.id: span.text for span in spans}),
    )
    sources = []
    for index, row in enumerate(fixture["sources"]):
        receipt = SourceReceipt(
            row.get("requested_url", row["url"]),
            row["url"],
            row.get("fetched_at", "2026-11-10T00:00:00Z"),
            _fixture_source_text(row),
            completeness=row.get("completeness", "complete"),
            published_at=row.get("published_at", ""),
            updated_at=row.get("updated_at", ""),
        )
        sources.append(
            SourceSnapshot(
                target.accepted_id,
                target.root,
                target.owner,
                f"fixture-read-{index}",
                receipt,
                _digest(asdict(receipt)),
            )
        )
    raw = {
        "target_digest": target.digest,
        "source_digest": request_payload(target, tuple(sources))["source_digest"],
        "claims": fixture["claims"],
    }
    return parse_verdict(json.dumps(raw), target, tuple(sources))


def test_captured_false_clean_verdict_cannot_support_missing_error_and_removed_api_names(tmp_path):
    verdict = _fixture_verdict(tmp_path, "captured_false_clean.json")

    assert verdict.status == "issues"
    for target_id, literal in [
        ("answer:30", "SyntaxError"),
        ("answer:60", "message_from_string"),
        ("answer:61", "c_buffer"),
    ]:
        finding = next(row for row in verdict.claims if target_id in row.targets)
        assert finding.kind == "unsupported"
        assert literal in finding.basis


def test_saved_genuine_supported_53_span_report_remains_supported(tmp_path):
    verdict = _fixture_verdict(tmp_path, "captured_supported_53.json")

    assert verdict.status == "supported"
    assert len(verdict.reviewed) == 53


def _review(tmp_path, target_text, source_text, *, kind="supported", basis="Karşılaştırıldı."):
    _, target, sources = target_sources(tmp_path, target_text)
    receipt = replace(sources[0].receipt, text=source_text)
    sources = (replace(sources[0], receipt=receipt, digest=_digest(asdict(receipt))),)
    payload = request_payload(target, sources)
    raw = {
        "target_digest": target.digest,
        "source_digest": payload["source_digest"],
        "claims": [
            {
                "targets": list(payload["target"]),
                "sources": list(payload["sources"][0]["spans"]),
                "kind": kind,
                "basis": basis,
            },
        ],
    }
    return parse_verdict(json.dumps(raw), target, sources)


@pytest.mark.parametrize(
    ("target", "source", "missing"),
    [
        ("It now raises `SyntaxError`.", "It emits a syntax warning.", "SyntaxError"),
        (
            "`read_record` and `write_record` were removed.",
            "read_record was removed.",
            "write_record",
        ),
        (
            "`widget.remove_item()` was removed.",
            "The widget module was updated.",
            "widget.remove_item",
        ),
        ("Use `--safe-mode`.", "Safe mode is available.", "--safe-mode"),
        ("Use `--safe-mode`.", "--safe-mode-extra", "--safe-mode"),
        ("Use `--safe-mode`.", "---safe-mode", "--safe-mode"),
        ("`read_record` changed.", "read_Record changed.", "read_record"),
        ("`alpha.fetch_item()` changed.", "beta.fetch_item() changed.", "alpha.fetch_item"),
        (
            "`np.asarray()` converts input to an array.",
            "import numpy as np. import other as np. numpy.asarray() converts input to an array.",
            "np.asarray",
        ),
        ("`np.asarray()` changed.", "import numpy as np.", "np.asarray"),
        (
            "`np.asarray()` changed.",
            "import numpy as np. np = other. numpy.asarray() changed.",
            "np.asarray",
        ),
        (
            "`np.asarray()` changed.",
            "import numpy as np. from other import value as np. numpy.asarray() changed.",
            "np.asarray",
        ),
        (
            "For this example, `local_counter` is our variable. `erase_item` was removed.",
            "Related module contents.",
            "erase_item",
        ),
        (
            "Now raises <code>NotFoundError</code>.",
            "A not found warning is emitted.",
            "NotFoundError",
        ),
    ],
)
def test_supported_label_needs_each_technical_literal_in_its_cited_spans(
    tmp_path, target, source, missing
):
    verdict = _review(tmp_path, target, source, basis=f"The answer contains {missing}.")

    assert verdict.status == "issues"
    assert verdict.claims[0].kind == "unsupported"
    assert missing in verdict.claims[0].basis


@pytest.mark.parametrize(
    ("target", "source"),
    [
        ("`read_record` changed.", "pkg.read_record was updated."),
        ("`widget.remove_item()` changed.", "widget . remove_item ( ) was updated."),
        ("`widget.remove_item()` changed.", "The widget module updates remove_item()."),
        ("`widget.remove_item()` changed.", "remove_item() was updated."),
        ("`SyntaxWarning` oluşur.", "A syntax warning is emitted."),
        ("`SyntaxError` oluşur.", "A SyntaxError is emitted."),
        (
            "<code>widget.remove_item()</code> changed.",
            "<code>widget</code> . <code>remove_item</code> ( ) updated.",
        ),
        ("Use `--safe-mode`.", "The --safe-mode option is supported."),
        ("`call_item()` changed.", "pkg.call_item() was updated."),
        ("`api::remove_item()` changed.", "api :: remove_item ( ) changed."),
        (
            "`np.asarray()` converts input to an array.",
            "import numpy as np. numpy.asarray() converts input to an array.",
        ),
        ("`local.fetch_item()` changed.", "import alpha as local. alpha.fetch_item() changed."),
    ],
)
def test_clear_literal_spelling_punctuation_and_basename_aliases_are_accepted(
    tmp_path, target, source
):
    assert _review(tmp_path, target, source).status == "supported"


@pytest.mark.parametrize(
    "target",
    [
        "Report saved as `report_final.md`.",
        "File saved as `report_final.custom`.",
        "Report saved as `src/report_final.md`.",
        "Report is at `https://example.test/report_final.md`.",
        "Version `3.14.0` is available.",
        "`güvenli yöntem` kullanılır.",
        "For this example, `local_counter` is our variable.",
        "`local_counter` is our example variable.",
        "Örnek değişkenimiz `local_counter` olsun.",
        "Set `local_counter = 1` in this example.",
        "Example:\n```python\nlocal_counter = read_record()\n```",
        "Erstellt eine sichere Verbindung ohne zusätzliche Variablen.",
        "La fonction crée une connexion sûre.",
        "A source-honest ordinary translated statement.",
    ],
)
def test_delivery_names_authored_examples_and_ordinary_prose_are_not_symbol_requirements(
    tmp_path, target
):
    assert _review(tmp_path, target, "Related ordinary source statement.").status == "supported"


def test_literal_presence_does_not_clear_a_semantic_failure(tmp_path):
    verdict = _review(
        tmp_path,
        "`read_record` was removed.",
        "read_record was introduced, not removed.",
        kind="contradicted",
        basis="The same API has the opposite lifecycle claim.",
    )

    assert verdict.status == "issues"
    assert verdict.claims[0].basis == "The same API has the opposite lifecycle claim."


@pytest.mark.parametrize("name", ["erase_item", "SyntaxError"])
def test_cannot_borrow_literal_from_uncited_owned_span_or_judge_basis(tmp_path, name):
    text = "`erase_item` was removed." if name == "erase_item" else "It raises SyntaxError."
    _, target, sources = target_sources(tmp_path, text)
    receipt = replace(sources[0].receipt, text="Module contents.\n" * 40 + name + " mentioned.")
    sources = (replace(sources[0], receipt=receipt, digest=_digest(asdict(receipt))),)
    payload = request_payload(target, sources)
    spans = payload["sources"][0]["spans"]
    assert name not in spans["s1:1"]
    raw = {
        "target_digest": target.digest,
        "source_digest": payload["source_digest"],
        "claims": [
            {
                "targets": list(payload["target"]),
                "sources": ["s1:1"],
                "kind": "supported",
                "basis": f"The source contains {name}.",
            }
        ],
    }

    verdict = parse_verdict(json.dumps(raw), target, sources)

    assert verdict.status == "issues"
    assert name in verdict.claims[0].basis


@pytest.mark.parametrize("name", ["read_record", "SyntaxError"])
def test_reader_receipt_url_cannot_supply_page_api_evidence(tmp_path, name):
    text = "`read_record` was removed." if name == "read_record" else "It raises SyntaxError."
    _, target, sources = target_sources(tmp_path, text)
    receipt = replace(
        sources[0].receipt,
        requested_url=f"https://example.test/api/{name}",
        final_url=f"https://example.test/api/{name}",
        text="Module overview.",
    )
    sources = (replace(sources[0], receipt=receipt, digest=_digest(asdict(receipt))),)
    payload = request_payload(target, sources)
    raw = {
        "target_digest": target.digest,
        "source_digest": payload["source_digest"],
        "claims": [
            {
                "targets": list(payload["target"]),
                "sources": ["s1:receipt"],
                "kind": "supported",
                "basis": "The reader URL contains the API name.",
            }
        ],
    }

    verdict = parse_verdict(json.dumps(raw), target, sources)

    assert verdict.status == "issues"
    assert name in verdict.claims[0].basis


def test_import_alias_cannot_be_borrowed_from_uncited_span_or_judge_basis(tmp_path):
    _, target, sources = target_sources(tmp_path, "`np.asarray()` changed.")
    receipt = replace(
        sources[0].receipt,
        text="numpy.asarray() changed.\n" * 40 + "import numpy as np.",
    )
    sources = (replace(sources[0], receipt=receipt, digest=_digest(asdict(receipt))),)
    payload = request_payload(target, sources)
    assert "import numpy as np" not in payload["sources"][0]["spans"]["s1:1"]
    raw = {
        "target_digest": target.digest,
        "source_digest": payload["source_digest"],
        "claims": [
            {
                "targets": list(payload["target"]),
                "sources": ["s1:1"],
                "kind": "supported",
                "basis": "import numpy as np; explicit alias.",
            }
        ],
    }

    verdict = parse_verdict(json.dumps(raw), target, sources)

    assert verdict.status == "issues"
    assert "np.asarray" in verdict.claims[0].basis


@pytest.mark.parametrize(
    ("target", "source", "missing"),
    [
        (
            "finally çıkışı artık yasaktır (SyntaxError).",
            "PEP 765: Disallow control flow that exits a finally block.",
            "SyntaxError",
        ),
        ("It raises SyntaxError.", "It emits SyntaxWarning.", "SyntaxError"),
        ("It raises ValueError.", "A value warning is emitted.", "ValueError"),
        ("It emits RuntimeWarning.", "RuntimeError is raised.", "RuntimeWarning"),
        ("It raises CustomException.", "An exception is raised.", "CustomException"),
        ("It raises <strong>SyntaxError</strong>.", "SyntaxWarning.", "SyntaxError"),
    ],
)
def test_plain_error_type_requires_its_own_cited_evidence(tmp_path, target, source, missing):
    verdict = _review(tmp_path, target, source, basis=f"The answer contains {missing}.")

    assert verdict.status == "issues"
    assert verdict.claims[0].kind == "unsupported"
    assert missing in verdict.claims[0].basis


@pytest.mark.parametrize(
    ("target", "source"),
    [
        ("It raises SyntaxError.", "It raises SyntaxError."),
        ("It emits SyntaxWarning.", "A syntax warning is emitted."),
        ("It raises ValueError.", "A value error is raised."),
        ("It emits RuntimeWarning.", "A runtime warning is emitted."),
        ("It raises CustomException.", "A custom exception is raised."),
    ],
)
def test_plain_error_type_accepts_existing_source_spelling_semantics(tmp_path, target, source):
    assert _review(tmp_path, target, source).status == "supported"


@pytest.mark.parametrize(
    "target",
    [
        "Error, Warning and Exception describe ordinary categories.",
        "A SyntaxErrorish or mySyntaxErrorHandler label is ordinary text.",
        "An example uses CustomException.",
        "CustomException is an example variable.",
        "Örnek değişkenimiz CustomException olsun.",
        "Report saved as SyntaxError.custom.",
        "Read SyntaxError.md.",
        "Read src/SyntaxError or C:\\temp\\SyntaxError.",
        "See https://example.test/SyntaxError for details.",
        "See https://SyntaxError.example.test for details.",
        "Example:\n```python\nraise SyntaxError\n```",
        "<pre>raise SyntaxError</pre>",
        "<script>SyntaxError</script><style>RuntimeWarning</style>",
        "<!-- SyntaxError -->Ordinary text.",
        "The attribute <span title='SyntaxError'>is ordinary text</span>.",
        "Use `raise SyntaxError`.",
    ],
)
def test_plain_error_names_preserve_conservative_nonclaim_exclusions(tmp_path, target):
    assert _review(tmp_path, target, "Related ordinary source statement.").status == "supported"


def test_authored_occurrence_does_not_hide_later_plain_factual_occurrence(tmp_path):
    verdict = _review(
        tmp_path,
        "Our example uses CustomException. It now raises CustomException.",
        "Module overview.",
    )

    assert verdict.status == "issues"
    assert "CustomException" in verdict.claims[0].basis

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


def test_cannot_borrow_literal_from_uncited_owned_span_or_judge_basis(tmp_path):
    _, target, sources = target_sources(tmp_path, "`erase_item` was removed.")
    receipt = replace(sources[0].receipt, text="Module contents.\n" * 40 + "erase_item removed.")
    sources = (replace(sources[0], receipt=receipt, digest=_digest(asdict(receipt))),)
    payload = request_payload(target, sources)
    spans = payload["sources"][0]["spans"]
    assert "erase_item" not in spans["s1:1"]
    raw = {
        "target_digest": target.digest,
        "source_digest": payload["source_digest"],
        "claims": [
            {
                "targets": list(payload["target"]),
                "sources": ["s1:1"],
                "kind": "supported",
                "basis": "The source contains erase_item.",
            }
        ],
    }

    verdict = parse_verdict(json.dumps(raw), target, sources)

    assert verdict.status == "issues"
    assert "erase_item" in verdict.claims[0].basis


def test_reader_receipt_url_cannot_supply_page_api_evidence(tmp_path):
    _, target, sources = target_sources(tmp_path, "`read_record` was removed.")
    receipt = replace(
        sources[0].receipt,
        requested_url="https://example.test/api/read_record",
        final_url="https://example.test/api/read_record",
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
    assert "read_record" in verdict.claims[0].basis


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

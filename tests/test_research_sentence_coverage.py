"""Bir paragrafın doğru başlangıcı, sonraki ayrı iddiayı kapsamış sayılmaz."""

from __future__ import annotations

import json

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract
from fusion_cli.engines.agent.research_grounding import parse_verdict, snapshot_target


def test_separate_report_sentence_cannot_hide_behind_supported_release_date(tmp_path):
    context = ToolContext(root=tmp_path)
    accept_delivery_contract(context, "Kaynaklı rapor hazırla.")
    text = (
        "<p>Orion 8.4.2 was released on 2031-10-25. "
        "This is the seventh maintenance release. "
        "The series has total support through 2035-10.</p>"
    )
    (tmp_path / "report.html").write_text(text)
    context.requested_outputs.add("report.html")
    target = snapshot_target(context, "")
    assert len(target.spans) == 3
    assert target.spans[1].text.strip() == "This is the seventh maintenance release."
    assert "".join(span.text for span in target.spans) == text
    assert all(text[span.start : span.end] == span.text for span in target.spans)
    # Tarih ve yaşam döngüsü incelense bile aradaki iddia atlanınca PASS olamaz.
    from fusion_cli.engines.agent.research_grounding import source_digest

    verdict = parse_verdict(
        json.dumps(
            {
                "target_digest": target.digest,
                "source_digest": source_digest(()),
                "claims": [
                    {
                        "targets": [target.spans[0].id, target.spans[-1].id],
                        "kind": "uncertain",
                        "sources": [],
                        "basis": "Only first and last sentences were assessed.",
                    }
                ],
            }
        ),
        target,
        (),
    )
    assert verdict.status == "incomplete"


def test_answer_sentences_are_separate_without_splitting_versions_or_dates(tmp_path):
    context = ToolContext(root=tmp_path)
    accept_delivery_contract(context, "Kısa kaynaklı yanıt ver.")
    text = "Orion 8.4.2 released 2031-10-25. It is supported."
    target = snapshot_target(context, text)
    assert [span.text for span in target.spans] == [
        "Orion 8.4.2 released 2031-10-25.",
        " It is supported.",
    ]
    assert [span.id for span in target.spans] == ["answer:1", "answer:2"]


def test_style_script_and_html_attributes_do_not_create_prose_sentence_boundaries(tmp_path):
    context = ToolContext(root=tmp_path)
    accept_delivery_contract(context, "Kaynaklı rapor hazırla.")
    text = (
        "<style>/* First. Second. */ body {font: 1.5em serif;}</style>"
        '<script>const label = "First. Second.";</script>'
        '<p title="First. Second.">Orion 8.4.2 is current. '
        'See <a href="https://example.org/a.b">source</a>.</p>'
    )
    (tmp_path / "report.html").write_text(text)
    context.requested_outputs.add("report.html")
    target = snapshot_target(context, "")
    assert len(target.spans) == 2
    assert "".join(span.text for span in target.spans) == text
    assert all(text[span.start : span.end] == span.text for span in target.spans)
    assert "8.4.2" in target.spans[0].text
    assert 'href="https://example.org/a.b"' in target.spans[1].text

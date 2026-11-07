"""Rapor yollarının tekilleştirilmesi kapsam ve tazelik sınırlarını korur."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.delivery_contract import accept_delivery_contract
from fusion_cli.engines.agent.research_grounding import snapshot_target


@pytest.fixture
def report_context(tmp_path):
    context = ToolContext(root=tmp_path)
    accept_delivery_contract(context, "Kaynaklara dayalı rapor hazırla.")
    (tmp_path / "report.html").write_text("<p>Orion 8.4.2: 2031-10-25.</p>")
    context.requested_outputs.add("report.html")
    return context


@pytest.mark.parametrize("alias", ["absolute", "dot", "symlink", "contract"])
def test_report_aliases_do_not_duplicate_review_or_change_digest(report_context, alias):
    context = report_context
    before = snapshot_target(context, "")
    if alias == "absolute":
        context.requested_outputs.add(str(context.root / "report.html"))
    elif alias == "dot":
        context.requested_outputs.add("./report.html")
    elif alias == "symlink":
        (context.root / "alias.html").symlink_to("report.html")
        context.requested_outputs.add("alias.html")
    else:
        context.delivery_contract.accepted = replace(
            context.delivery_contract.accepted,
            document_output=str(context.root / "report.html"),
        )
    after = snapshot_target(context, "")
    assert after.complete
    assert [span.text for span in after.spans] == ["<p>Orion 8.4.2: 2031-10-25.</p>"]
    assert after.spans == before.spans
    assert after.digest == before.digest


def test_equal_contents_at_distinct_paths_both_need_review(report_context):
    context = report_context
    (context.root / "other.html").write_text("<p>Orion 8.4.2: 2031-10-25.</p>")
    context.requested_outputs.add("other.html")
    target = snapshot_target(context, "")
    assert target.complete
    assert len(target.spans) == 2
    assert {span.location for span in target.spans} == {
        str(context.root / "report.html"),
        str(context.root / "other.html"),
    }


@pytest.mark.parametrize("invalid", ["missing", "outside", "symlink_outside"])
def test_valid_report_never_hides_invalid_output(report_context, invalid):
    context = report_context
    if invalid == "missing":
        context.requested_outputs.add("missing.html")
    else:
        outside = context.root.parent / "outside.html"
        outside.write_text("Outside content must never enter the review.")
        if invalid == "outside":
            context.requested_outputs.add(str(outside))
        else:
            (context.root / "escape.html").symlink_to(outside)
            context.requested_outputs.add("escape.html")
    target = snapshot_target(context, "")
    assert not target.complete
    assert [span.text for span in target.spans] == ["<p>Orion 8.4.2: 2031-10-25.</p>"]


def test_aliased_report_edit_invalidates_snapshot(report_context):
    context = report_context
    context.requested_outputs.add(str(context.root / "report.html"))
    before = snapshot_target(context, "")
    (context.root / "report.html").write_text("<p>Orion 8.4.2: 2031-10-26.</p>")
    after = snapshot_target(context, "")
    assert after.digest != before.digest
    assert after.spans != before.spans

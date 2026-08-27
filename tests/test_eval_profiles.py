from evals.direct_runner import extract_html
from evals.metrics import RunReport
from evals.profiles import EvalProfile, RunMetadata
from evals.report import report_from_dict, report_to_dict


def test_profiles_have_stable_cli_values():
    assert [profile.value for profile in EvalProfile] == [
        "fusion-full",
        "fusion-minimal",
        "direct",
    ]


def test_report_metadata_round_trips_and_legacy_reports_still_load():
    metadata = RunMetadata(suite="arena.yaml", profile="direct", model="model-x", repeat=3)
    restored = report_from_dict(report_to_dict(RunReport(results=(), metadata=metadata)))
    assert restored.metadata == metadata
    assert report_from_dict({"results": []}).metadata is None


def test_direct_extracts_one_fenced_or_raw_complete_document():
    fenced = "```html\n<!doctype html><html><body>x</body></html>\n```"
    raw = "<!doctype html><html><body>x</body></html>"
    assert extract_html(fenced) == raw
    assert extract_html(raw) == raw
    padded = f"\n{raw}\n"
    assert extract_html(padded) == padded


def test_direct_rejects_commentary_multiple_fences_and_incomplete_html():
    assert extract_html("Here you go\n```html\n<html></html>\n```") is None
    assert extract_html("```html\n<html></html>\n```\n```html\n<html></html>\n```") is None
    assert extract_html("<html><body>unfinished") is None
    assert extract_html("<html></html> trailing commentary") is None

"""Offline exact-id excerpts and owned evidence boundaries."""

import json
from dataclasses import replace

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent.research_grounding import capture_source, request_payload
from fusion_cli.tools import web

from .test_research_grounding import target_sources


@pytest.fixture
def reader(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "url_block_reason", lambda url: None)
    context = ToolContext(root=tmp_path)

    def read(body, section="late", content_type="text/html"):
        monkeypatch.setattr(
            web,
            "fetch_following_redirects",
            lambda url: (content_type, body, "https://final.test/page"),
        )
        args = {"url": "https://source.test/page"}
        if section is not None:
            args["section"] = section
        return web.web_fetch(args, context)

    return read, context


def test_late_nested_section_exact_decoded_id_and_links(reader):
    read, _ = reader
    body = "<html><p>" + "prefix " * 5000 + '</p><section id="late&amp;x">'
    body += '<h2>Late API</h2><p>nested <b>value</b><br>tail</p><a href="/api">docs</a>'
    body += "</section><p>excluded sibling</p></html>"
    prefix = read(body, None)
    result = read(body, "late&x")
    assert result.ok
    assert "Late API" not in prefix.source_receipt.text
    assert "Late API" in result.source_receipt.text
    assert "nested" in result.source_receipt.text
    assert "https://final.test/api" in result.source_receipt.text
    assert "excluded sibling" not in result.source_receipt.text
    assert "prefix" not in result.source_receipt.text
    assert result.source_receipt.scope == "section"
    assert result.source_receipt.section_id == "late&x"
    assert result.source_receipt.completeness == "truncated"
    assert result.source_receipt.requested_url == "https://source.test/page"


def test_heading_is_only_heading_not_invented_range(reader):
    read, _ = reader
    result = read('<h2 id="late">Title</h2><p>not heading content</p>')
    assert result.source_receipt.text == "Title"


@pytest.mark.parametrize(
    "body",
    [
        '<p id="other">missing</p>',
        '<p id="late">one</p><p id="late">two</p>',
        '<p id="late"></p>',
        '<div id="late"><b>bad</div>',
        '<div id="late">unclosed',
        '<div id="late"><p broken="x" <b>bad</b></p></div>',
        '<div id="late">' + "<div>" * 140 + "deep" + "</div>" * 141,
        '<p id="late">valid</p>' + "x" * web.MAX_FETCH_BYTES,
    ],
    ids=["missing", "duplicate", "empty", "mismatch", "unclosed", "malformed", "deep", "oversize"],
)
def test_invalid_selected_markup_never_falls_back_to_prefix(reader, body):
    read, _ = reader
    result = read(body)
    assert not result.ok
    assert result.source_receipt is None


@pytest.mark.parametrize("section", ["", "   ", 42, None, "x" * 513])
def test_selector_validation_precedes_io(monkeypatch, tmp_path, section):
    def forbidden(url):
        pytest.fail("I/O before selector validation")

    monkeypatch.setattr(web, "url_block_reason", forbidden)
    from fusion_cli.tools.args import ArgumentError

    with pytest.raises(ArgumentError):
        web.web_fetch(
            {"url": "https://source.test", "section": section}, ToolContext(root=tmp_path)
        )


def test_nonhtml_selection_fails(reader):
    read, _ = reader
    result = read("plain text", content_type="text/plain")
    assert not result.ok and result.source_receipt is None


def test_access_wall_outside_section_is_not_hidden(reader):
    read, _ = reader
    result = read('<p>Please enable javascript to continue</p><p id="late">claimed data</p>')
    assert "YETENEK_DUVARI" in result.output or "doğrulama" in result.output
    assert result.source_receipt is None


def test_early_cancellation_has_no_receipt(reader):
    read, context = reader
    context.cancelled.set()
    result = read('<p id="late">data</p>')
    assert not result.ok and result.source_receipt is None


def test_prefix_and_section_are_distinct_owned_sources(reader, tmp_path):
    read, _ = reader
    body = '<p>Prefix fact</p><p id="late">Section fact</p>'
    prefix, section = read(body, None), read(body)
    context, target, _ = target_sources(tmp_path)
    contract = context.delivery_contract.accepted
    sources = tuple(
        capture_source(r.source_receipt, contract, str(i)) for i, r in enumerate((prefix, section))
    )
    payload = request_payload(target, sources)
    assert len(payload["sources"]) == 2
    assert sources[0].digest != sources[1].digest
    metadata = json.loads(payload["sources"][1]["spans"]["s2:receipt"])
    assert metadata["scope"] == "section" and metadata["section_id"] == "late"
    assert "late" not in payload["sources"][1]["spans"]["s2:1"]
    for field in ("accepted_id", "root", "owner"):
        assert not request_payload(target, (replace(sources[1], **{field: "other"}),))["sources"]
    tampered = replace(sources[1], receipt=replace(sources[1].receipt, section_id="forged"))
    assert not request_payload(target, (tampered,))["sources"]
    for changes in ({"section_id": ""}, {"completeness": "complete"}):
        invalid = capture_source(replace(section.source_receipt, **changes), contract, "bad")
        assert not request_payload(target, (invalid,))["sources"]


@pytest.mark.parametrize(
    "body",
    [
        '<p id="late">fact</p broken>',
        '<p id="late" ' + " " * 100_000 + "<b>bad</b>",
        '<p id="late" data="' + "x" * 100_000,
        "<script>" * 10_000 + '<p id="late">not an actual element</p>',
    ],
    ids=["bad-end", "long-space", "long-attribute", "unclosed-scripts"],
)
def test_malformed_boundaries_fail_without_receipt(reader, body):
    read, _ = reader
    result = read(body)
    assert not result.ok and result.source_receipt is None


def test_hidden_content_is_not_visible_evidence_but_real_duplicate_ids_fail(reader):
    read, _ = reader
    hidden = "<script>hidden_script_fact</script><style>hidden_style_fact</style>"
    hidden += "<noscript>hidden_noscript_fact</noscript>"
    result = read('<section id="late">visible' + hidden + "</section>")
    assert result.source_receipt.text == "visible"
    result = read(
        '<section id="late">visible</section><noscript><p id="late">duplicate</p></noscript>'
    )
    assert not result.ok and result.source_receipt is None


def test_boolean_attributes_and_multiline_markup_are_valid(reader):
    read, _ = reader
    result = read('<section hidden class="x" id="late">\n<p>Fact</p>\n</section>')
    assert result.ok and "Fact" in result.source_receipt.text


def test_huge_incomplete_token_is_rejected_before_whole_response_scan():
    from fusion_cli.tools.web_sections import SectionError, select_section

    checks = []

    def cancelled():
        checks.append(True)
        return False

    with pytest.raises(SectionError):
        select_section(
            '<p id="late" attr="' + "x" * (web.MAX_FETCH_BYTES - 100), "late", cancelled=cancelled
        )
    assert len(checks) < 10


def test_selection_inside_hidden_ancestor_is_empty(reader):
    read, _ = reader
    result = read('<noscript><p id="late">hidden fact</p></noscript>')
    assert not result.ok and result.source_receipt is None


def test_wire_cap_is_preserved_for_multibyte_decoding(reader, monkeypatch):
    import httpx

    read, _ = reader
    body = '<p id="late">fact</p>'
    wire = body.encode("utf-16-le")
    monkeypatch.setattr(web, "MAX_FETCH_BYTES", len(wire))
    response = httpx.Response(
        200, content=wire, headers={"content-type": "text/html; charset=utf-16-le"}
    )
    capped = web._read_capped(response)
    assert capped == body and len(capped.encode()) < len(wire)
    result = read(capped)
    assert not result.ok and result.source_receipt is None


def test_cancel_during_selection_has_no_receipt(reader, monkeypatch):
    from fusion_cli.tools import web_sections

    read, context = reader
    original = web_sections._SectionParser.handle_data

    def cancel(parser, data):
        context.cancelled.set()
        original(parser, data)

    monkeypatch.setattr(web_sections._SectionParser, "handle_data", cancel)
    result = read('<p id="late">data</p>')
    assert not result.ok and result.source_receipt is None


def test_selector_metadata_cannot_supply_api_literal(reader, tmp_path):
    from fusion_cli.engines.agent import research_grounding as g

    read, _ = reader
    selector = "api.secret_endpoint"
    result = read(f'<p id="{selector}">Unrelated visible text</p>', selector)
    context, target, _ = target_sources(tmp_path, "`api.secret_endpoint` is supported.")
    source = capture_source(result.source_receipt, context.delivery_contract.accepted, "section")
    payload = request_payload(target, (source,))
    verdict = g.parse_verdict(
        json.dumps(
            {
                "target_digest": payload["target_digest"],
                "source_digest": payload["source_digest"],
                "claims": [
                    {
                        "targets": list(payload["target"]),
                        "kind": "supported",
                        "sources": ["s1:receipt"],
                        "basis": "claimed from metadata",
                    }
                ],
            }
        ),
        target,
        (source,),
    )
    assert verdict.status == "issues"


@pytest.mark.parametrize("replacement", [None, "withheld section body"])
async def test_actor_keeps_prefix_and_section_distinct_and_rejects_replaced_output(
    monkeypatch, tmp_path, replacement
):
    from fusion_cli.engines.agent import loop
    from fusion_cli.engines.agent.execution_policy import ExecutionPolicy
    from fusion_cli.engines.agent.hook_bridge import ToolNote

    from .fakes import RecordingSink, ScriptedProvider, model_result, tool_call
    from .test_agent_loop import _deps, _kur
    from .test_research_grounding import typed_clean

    url = "https://orion.example/page"
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=[tool_call("web_fetch", url=url)]),
                model_result(tool_calls=[tool_call("web_fetch", url=url, section="late")]),
                model_result("Research completed."),
            ]
        ),
    )
    fetches = []

    def fetch(url):
        fetches.append(url)
        return "text/html", '<p>Prefix fact</p><p id="late">Section fact</p>', url

    monkeypatch.setattr(web, "url_block_reason", lambda url: None)
    monkeypatch.setattr(web, "fetch_following_redirects", fetch)

    async def post_hook(*args, **kwargs):
        return ToolNote(replaced_output=replacement)

    async def judge(prompt, *args, **kwargs):
        return model_result(typed_clean(prompt))

    monkeypatch.setattr(loop, "post_tool_use", post_hook)
    monkeypatch.setattr(loop.review, "_ask", judge)
    deps = _deps(tmp_path, RecordingSink())
    deps.execution = ExecutionPolicy(
        is_web=False, requires_web_lookup=True, heuristic_auto_continue=False
    )
    await loop.run_agent("Research Orion", deps)
    sources = deps.require_budget().research_sources
    assert fetches == [url, url]
    if replacement:
        assert sources == []
    else:
        assert [source.receipt.scope for source in sources] == ["document", "section"]
        assert sources[0].digest != sources[1].digest


def test_wall_in_late_selected_excerpt_never_mints_section_receipt(reader):
    read, _ = reader
    result = read(
        "<p>" + "prefix " * 1000 + '</p><p id="late">Please enable javascript to continue</p>'
    )
    assert result.source_receipt is None


def test_default_output_is_byte_compatible_and_selected_dates_are_preserved(reader):
    from .test_web_provenance_remediation import FixedClock

    read, context = reader
    body = '<meta property="article:published_time" content="2026-11-01"><p id="late">Fact</p>'
    read(body)
    result = web.web_fetch({"url": "https://source.test/page"}, context, clock=FixedClock())
    assert result.output == (
        "Kaynak: https://final.test/page\nİstenen URL: https://source.test/page\n"
        "Erişim zamanı: 2026-11-04T00:00:00+00:00\n\nFact"
    )
    section = web.web_fetch(
        {"url": "https://source.test/page", "section": "late"}, context, clock=FixedClock()
    )
    assert section.source_receipt.published_at == "2026-11-01"
    assert section.source_receipt.fetched_at == "2026-11-04T00:00:00+00:00"


def test_access_wall_cannot_hide_behind_empty_markup(reader):
    read, _ = reader
    body = "<span></span>" * 3000 + "<p>Please enable javascript to continue</p>"
    result = read(body + '<p id="late">claimed data</p>')
    assert not result.ok and result.source_receipt is None


@pytest.mark.parametrize("tag", ["script", "style", "noscript", "div"])
@pytest.mark.parametrize("position", ["selected", "ancestor"])
def test_nonvoid_selfclosing_markup_fails_without_receipt(reader, tag, position):
    read, _ = reader
    body = (
        f'<section id="late"><{tag}/>hidden_fact</section>'
        if position == "selected"
        else f'<{tag}/><section id="late">hidden_fact</section>'
    )
    result = read(body)
    assert not result.ok and result.source_receipt is None


@pytest.mark.parametrize("closing_tag", ["script", "style"])
@pytest.mark.parametrize("position", ["selected", "ancestor"])
def test_unmatched_hidden_closing_tag_cannot_release_noscript(reader, closing_tag, position):
    read, _ = reader
    body = (
        f'<section id="late"><noscript></{closing_tag}>hidden_fact</noscript></section>'
        if position == "selected"
        else f'<noscript></{closing_tag}><section id="late">hidden_fact</section></noscript>'
    )
    result = read(body)
    assert not result.ok and result.source_receipt is None


@pytest.mark.parametrize("tag", ["br", "img", "input"])
def test_valid_void_selfclosing_markup_still_renders(reader, tag):
    read, _ = reader
    result = read(f'<section id="late">before<{tag}/>after</section>')
    assert result.ok
    assert "before" in result.source_receipt.text and "after" in result.source_receipt.text


def test_unrelated_closings_cannot_bypass_hidden_ancestor_limit(reader):
    read, _ = reader
    # Keep overflow after the access probe's first chunk; only 4,001 chars are visible.
    body = "x" * 4001 + "<!--" + " " * 20_000 + "-->"
    body += "<noscript></div>" * 129 + "</noscript>" * 129
    result = read(body + '<p id="late">fact</p>')
    assert not result.ok and result.source_receipt is None


def test_hidden_ancestor_overflow_stops_before_large_tail():
    from fusion_cli.tools.web_sections import SectionError, select_section

    body = "x" * 4001 + "<noscript></div>" * 129 + "</noscript>" * 129
    body += '<p id="late">fact</p>' + "tail" * 200_000
    checks = []

    def cancelled():
        checks.append(True)
        return False

    with pytest.raises(SectionError, match="Hidden markup nesting limit exceeded"):
        select_section(body, "late", cancelled=cancelled)
    assert len(checks) == 1

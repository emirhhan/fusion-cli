"""Real DOM regressions for target-size exception handling; no external requests."""

from pathlib import Path

import pytest

from fusion_cli.engines.agent.browser_verify import _LAYOUT_PROBE
from fusion_cli.engines.agent.web_verify import inspect_web_output_by_severity


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.mark.parametrize("width", [375, 768, 1440])
@pytest.mark.parametrize(
    ("markup", "count"),
    [
        ('<p>Kaynak: <a href="https://example.invalid">Python release announcement</a></p>', 0),
        ("<button>x</button>", 0),
        ('<p><strong>Kaynak:</strong> <a href="#x">x</a><a href="#y">y</a></p>', 0),
        ('<div class="row" style="gap:24px"><button>x</button><button>y</button></div>', 0),
        ('<div class="row" style="gap:8px"><button>x</button><button>y</button></div>', 0),
        ('<div class="row"><button>x</button><button>y</button></div>', 2),
        ('<div class="row"><button>x</button><span role="button">y</span></div>', 2),
        ('<div class="row"><button>x</button><span onclick="void(0)">y</span></div>', 2),
        (
            '<div class="row"><button>x</button><button style="visibility:hidden">y</button></div>',
            0,
        ),
        ('<div class="row"><a href="#x">x</a><a href="#y">y</a></div>', 2),
    ],
)
def test_exceptions_keep_crowded_targets(browser, width, markup, count):
    context = browser.new_context(viewport={"width": width, "height": 900})
    requests = []
    context.route("**/*", lambda route: (requests.append(route.request.url), route.abort()))
    try:
        page = context.new_page()
        page.set_content(
            "<style>.row{display:flex;gap:0}button,[role=button],[onclick],.row>a"
            "{box-sizing:border-box;width:16px;height:16px;padding:0;border:0;display:block}</style>"
            + markup
        )
        assert len(page.evaluate(_LAYOUT_PROBE)["smallTargets"]) == count
        assert requests == []
    finally:
        context.close()


@pytest.mark.parametrize(
    "landmark",
    [
        "<main>x</main>",
        '<div role="main">x</div>',
        "<div role=main>x</div>",
        '<div role=" main ">x</div>',
    ],
)
def test_main_landmarks_do_not_produce_recommendations(landmark):
    assert inspect_web_output_by_severity(
        {"x.html": "<html><body>" + landmark + "</body></html>"}
    ) == ((), (), ())


def test_main_recommendation_is_advisory_not_warning():
    blocking, warnings, advisories = inspect_web_output_by_severity(
        {"x.html": "<html><body><p>x</p></body></html>"}
    )
    assert blocking == warnings == ()
    assert len(advisories) == 1


def test_commented_main_is_not_a_landmark():
    _, _, advisories = inspect_web_output_by_severity(
        {"x.html": "<html><body><!-- <main> --><p>x</p></body></html>"}
    )
    assert len(advisories) == 1


@pytest.mark.parametrize("width", [375, 768, 1440])
def test_actual_report_citation_is_not_a_target_warning(browser, width):
    context = browser.new_context(viewport={"width": width, "height": 900})
    requests = []
    context.route("**/*", lambda route: (requests.append(route.request.url), route.abort()))
    try:
        page = context.new_page()
        page.set_content(
            Path(__file__)
            .with_name("fixtures")
            .joinpath("target_exception_report.html")
            .read_text()
        )
        assert page.evaluate(_LAYOUT_PROBE)["smallTargets"] == []
        assert requests == []
    finally:
        context.close()


def test_truncated_candidates_cannot_prove_spacing(browser):
    context = browser.new_context()
    context.route("**/*", lambda route: route.abort())
    try:
        page = context.new_page()
        page.set_content(
            "<style>button{display:block;width:16px;height:16px;padding:0;border:0;margin:30px}</style>"
            + "<button>x</button>" * 1501
        )
        assert len(page.evaluate(_LAYOUT_PROBE)["smallTargets"]) == 1500
    finally:
        context.close()

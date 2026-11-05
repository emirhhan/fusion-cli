"""The real extension reader reports the document URL with its visible text."""

import pytest

from tests.test_chrome_page_action import _page_action_source

playwright = pytest.importorskip("playwright.sync_api")
URL = "http://127.0.0.1:53391/index.html"


@pytest.fixture(scope="module")
def page():
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        context = browser.new_context(service_workers="block")

        def route(request):
            if request.request.url == URL:
                request.fulfill(
                    body="<title>Local demo</title><main>Demo: messages are not sent.</main>",
                    content_type="text/html",
                )
            else:
                request.abort()

        context.route("**/*", route)
        result = context.new_page()
        result.goto(URL)
        yield result
        context.close()
        browser.close()


def test_full_text_reader_reports_actual_url_instead_of_supplied_url(page):
    source = _page_action_source()
    result = page.evaluate(
        f"args => ({source})('text_page', args)",
        {"url": "https://forged.test/", "__taskOrigin": "http://127.0.0.1:53391"},
    )
    assert result.get("url") == URL
    assert result["title"] == "Local demo"
    assert "messages are not sent" in result["text"]


def test_text_reader_keeps_existing_accepted_origin_guard(page):
    source = _page_action_source()
    with pytest.raises(playwright.Error, match="başlangıçtaki sitesi değişti"):
        page.evaluate(
            f"args => ({source})('text_page', args)", {"__taskOrigin": "https://foreign.test"}
        )

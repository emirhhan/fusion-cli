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


@pytest.mark.parametrize("text", ["A" * 20_000, "😀" * 10_000], ids=["ascii", "emoji"])
def test_text_boundary_keeps_visible_following_notice_on_next_page(page, text):
    # Native JS length is 20,000 for both fixtures; Python len differs for emoji.
    page.set_content("<main></main><p>Visible following notice.</p>")
    page.locator("main").evaluate("(el, text) => { el.textContent = text; }", text)
    assert page.locator("p").is_visible()
    source = _page_action_source()
    first = page.evaluate(f"args => ({source})('text_page', args)", {"page": 1})
    second = page.evaluate(f"args => ({source})('text_page', args)", {"page": 2})
    assert first["text"] == text
    assert first["has_more"] is True
    assert second["text"] == "\nVisible following notice."
    assert second["has_more"] is False


@pytest.mark.parametrize("size,has_more", [(19_999, False), (20_000, False), (20_001, True)])
def test_text_reader_reports_exhaustion_for_single_node(page, size, has_more):
    page.set_content("<main></main>")
    page.locator("main").evaluate("(el, size) => { el.textContent = 'A'.repeat(size); }", size)
    source = _page_action_source()
    first = page.evaluate(f"args => ({source})('text_page', args)", {"page": 1})
    assert first["text"] == "A" * min(size, 20_000)
    assert first["has_more"] is has_more


def test_text_reader_preserves_inline_block_separators_at_later_page_boundary(page):
    page.set_content("<main></main><span>B</span><p>Following notice.</p>")
    page.locator("main").evaluate("el => { el.textContent = 'A'.repeat(39998); }")
    source = _page_action_source()
    second = page.evaluate(f"args => ({source})('text_page', args)", {"page": 2})
    third = page.evaluate(f"args => ({source})('text_page', args)", {"page": 3})
    assert second["text"] == "A" * 19_998 + " B"
    assert second["has_more"] is True
    assert third["text"] == "\nFollowing notice."
    assert third["has_more"] is False

"""URL input must preserve schemes so access policy can reject them before I/O."""

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.tools import browser, web


@pytest.mark.parametrize("normalize", [browser.normalize_url, web._normalize_url])
@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/report.html",
        "file:123",
        "FILE:///tmp/report.html",
        "ftp://example.com/a",
        "gopher://example.com/a",
        "data:text/html,<b>x</b>",
        "javascript:alert(1)",
        "about:blank",
        "chrome://settings",
        "custom+test:payload",
        "HTTP://example.com/a",
        "HTTPS://example.com/a",
    ],
)
def test_explicit_scheme_is_preserved_for_access_policy(normalize, url):
    assert normalize(url) == url


@pytest.mark.parametrize(
    "normalize, prefix", [(browser.normalize_url, "http"), (web._normalize_url, "https")]
)
@pytest.mark.parametrize("host", ["localhost:5173", "127.0.0.1:5173", "[::1]:5173"])
def test_bare_loopback_host_port_keeps_existing_scheme_default(normalize, prefix, host):
    assert normalize(host + "/a") == f"{prefix}://{host}/a"


@pytest.mark.parametrize("normalize", [browser.normalize_url, web._normalize_url])
@pytest.mark.parametrize("host", ["example.com", "example.com:8443", "192.0.2.1:8080"])
def test_bare_public_domain_and_ip_are_completed(normalize, host):
    assert normalize(host + "/a") == f"https://{host}/a"


@pytest.mark.parametrize(
    "url", ["file:///tmp/report.html", "ftp://example.com/a", "data:text/html,x"]
)
async def test_unsupported_scheme_rejected_by_both_tools_without_dns_or_browser(
    tmp_path, monkeypatch, url
):
    def unexpected(*args, **kwargs):
        pytest.fail("unsupported schemes must be rejected before network or browser access")

    monkeypatch.setattr(web.socket, "getaddrinfo", unexpected)
    monkeypatch.setattr(browser, "_sayfa", unexpected)
    context = ToolContext(tmp_path)
    for result in (
        web.web_fetch({"url": url}, context),
        await browser.browser_open({"url": url}, context),
    ):
        assert not result.ok
        assert "http/https" in result.output
        assert url.split(":", 1)[0] in result.output


async def test_local_file_rejection_explains_preview_recovery(tmp_path):
    url = "file:///tmp/report.html"
    context = ToolContext(tmp_path)
    results = [
        web.web_fetch({"url": url}, context),
        await browser.browser_open({"url": url}, context),
    ]
    for result in results:
        assert not result.ok
        assert "start_preview" in result.output
        assert "HTTP" in result.output
        assert "browser_open" in result.output


@pytest.mark.parametrize("scheme", ["file", "ftp", "gopher", "ws", "custom+test"])
async def test_allowed_local_origin_cannot_authorize_unsupported_protocol(
    tmp_path, monkeypatch, scheme
):
    def unexpected(*args, **kwargs):
        pytest.fail("preview permission cannot authorize unsupported protocol I/O")

    monkeypatch.setattr(web.socket, "getaddrinfo", unexpected)
    monkeypatch.setattr(browser, "_sayfa", unexpected)
    context = ToolContext(tmp_path)
    context.local_origins.add("localhost:5173")
    result = await browser.browser_open({"url": f"{scheme}://localhost:5173/private"}, context)
    assert not result.ok
    assert "http/https" in result.output
    if scheme == "file":
        assert "start_preview" in result.output


@pytest.mark.parametrize("scheme", ["http", "https", "HTTP", "HTTPS"])
def test_allowed_local_origin_remains_available_for_supported_protocols(scheme):
    assert web.browser_block_reason(f"{scheme}://localhost:5173/", {"localhost:5173"}) is None

"""Offline real-Chromium regression coverage for contact receipt claims."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.engines.agent.contact_form_probe import probe_contact_forms

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def browser():
    from playwright.async_api import async_playwright

    async with async_playwright() as driver:
        browser = await driver.chromium.launch()
        yield browser
        assert not browser.contexts
        await browser.close()


def form(handler: str, *, disclosure: str = "", extra: str = "") -> str:
    return f"""<section><h2>Contact</h2>{disclosure}<form id="contactForm">
    <input name="name"><input type="email" name="email"><input name="subject">
    <textarea name="message"></textarea><button>Send message</button></form>
    <p id="formStatus"></p></section>{extra}<script>
    const form = document.getElementById('contactForm');
    const status = document.getElementById('formStatus');
    form.addEventListener('submit', function(e) {{e.preventDefault(); {handler}}});
    </script>"""


@pytest.mark.parametrize(
    "receipt",
    [
        "Teşekkürler! Mesajınız başarıyla alındı. En kısa sürede size dönüş yapacağız.",
        "Thank you! Your message has been received. We will get back to you shortly.",
    ],
)
async def test_timer_receipt_without_transport_is_blocking(browser, receipt):
    html = form(f"setTimeout(() => {{status.textContent = {receipt!r}; form.reset();}}, 1000)")
    results = await probe_contact_forms(browser, html)
    assert results[0].status == "false_receipt"
    assert receipt in results[0].visible_receipt
    assert results[0].transport_attempts == 0


@pytest.mark.parametrize(
    "handler, disclosure",
    [
        ("status.textContent='Your message has been received (demo only; nothing sent).';", ""),
        (
            "status.textContent='Your message has been received.';",
            "<p>Demo form — no message is sent.</p>",
        ),
        ("localStorage.setItem('draft', 'hello');status.textContent='Draft saved locally';", ""),
    ],
)
async def test_honest_local_behavior_does_not_block(browser, handler, disclosure):
    result = (await probe_contact_forms(browser, form(handler, disclosure=disclosure)))[0]
    assert result.status == "observed_no_false_receipt"


async def test_hidden_demo_disclaimer_does_not_excuse_false_receipt(browser):
    result = (
        await probe_contact_forms(
            browser,
            form(
                "status.textContent='Your message was sent successfully';",
                disclosure="<p hidden>Demo form</p>",
            ),
        )
    )[0]
    assert result.status == "false_receipt"


@pytest.mark.parametrize(
    "handler",
    [
        "fetch('http://127.0.0.1:9876/send', {method:'POST',body:'qa'}).catch(()=>{});",
        "new Image().src='http://127.0.0.1:9876/send?message=qa';",
        "location.href='http://127.0.0.1:9876/send?message=qa';",
        "navigator.sendBeacon('http://127.0.0.1:9876/send','qa');",
        "window.open('mailto:qa@example.invalid?body=qa');",
        "form.submit();",
        "location.href='mailto:qa@example.invalid?body=qa';",
    ],
)
async def test_attempted_transport_never_verifies_delivery(browser, handler):
    received = []

    async def accept(reader, writer):
        received.append(await reader.read(2048))
        writer.close()

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    handler = handler.replace("9876", str(port))
    try:
        result = (
            await probe_contact_forms(
                browser, form(handler + "status.textContent='Your message has been received';")
            )
        )[0]
        assert result.status in {"unverified_transport", "not_measured"}
        assert result.transport_attempts > 0 or result.status == "not_measured"
        assert not received
    finally:
        server.close()
        await server.wait_closed()


async def test_external_script_missing_is_explicitly_unmeasured(browser):
    result = (
        await probe_contact_forms(
            browser,
            form(
                "status.textContent='Your message has been received';",
                extra='<script src="https://example.invalid/handler.js"></script>',
            ),
        )
    )[0]
    assert result.status == "not_measured"


@pytest.mark.parametrize(
    "html",
    [
        '<form><input type="search"><button>Search</button></form>',
        '<form><input type="number"><button>Calculate</button></form>',
    ],
)
async def test_non_contact_controls_are_not_submitted(browser, html):
    assert await probe_contact_forms(browser, html) == ()


async def test_hung_handler_has_bounded_cleanup(browser):
    result = await asyncio.wait_for(
        probe_contact_forms(browser, form("while(true){}"), timeout_s=2), 8
    )
    assert result[0].status == "not_measured"


async def test_browser_result_preserves_layout_and_blocks_false_receipt():
    from fusion_cli.core.evidence import EvidenceStatus
    from fusion_cli.engines.agent.browser_verify import PageObservation, browser_verification_result
    from fusion_cli.engines.agent.contact_form_probe import ContactObservation

    result = browser_verification_result(
        (
            PageObservation(
                name="index.html",
                overflowing=((375, 500),),
                contact_forms=(
                    ContactObservation("false_receipt", visible_receipt="Your message was sent"),
                ),
            ),
        ),
        source="browser",
    )
    assert not result.ok
    assert any("500" in item for item in result.findings)
    assert any("Your message was sent" in item for item in result.findings)
    assert any(
        item.criterion_id == "contact_receipt_truth" and item.status == EvidenceStatus.FAILED
        for item in result.evidence
    )


async def test_browser_result_does_not_claim_delivery_for_blocked_transport():
    from fusion_cli.core.evidence import EvidenceStatus
    from fusion_cli.engines.agent.browser_verify import PageObservation, browser_verification_result
    from fusion_cli.engines.agent.contact_form_probe import ContactObservation

    result = browser_verification_result(
        (
            PageObservation(
                name="index.html",
                contact_forms=(ContactObservation("unverified_transport", transport_attempts=1),),
            ),
        ),
        source="browser",
    )
    assert result.ok
    assert result.warnings
    assert any(
        item.criterion_id == "contact_receipt_truth" and item.status == EvidenceStatus.UNVERIFIED
        for item in result.evidence
    )


async def test_original_captured_site_timer_executes_in_isolation(browser):
    from pathlib import Path

    captured = Path(__file__).parent / "fixtures/contact_timer_receipt.html"
    result = (await probe_contact_forms(browser, captured.read_text()))[0]
    assert result.status == "false_receipt"
    assert "Mesajınız başarıyla alındı" in result.visible_receipt
    assert result.transport_attempts == 0


@pytest.mark.parametrize(
    "handler",
    [
        "const script=document.createElement('script');script.src='https://example.invalid/a.js';document.body.append(script);",
        "try {new WebSocket('wss://example.invalid/send')} catch(e) {}",
        "try {new Worker('https://example.invalid/a.js')} catch(e) {}",
    ],
)
async def test_unsupported_dynamic_browser_paths_are_unmeasured(browser, handler):
    result = (
        await probe_contact_forms(
            browser, form(handler + "status.textContent='Your message has been received';")
        )
    )[0]
    assert result.status == "not_measured"


async def test_unrelated_demo_text_does_not_excuse_contact_receipt(browser):
    result = (
        await probe_contact_forms(
            browser,
            "<article>Interactive demo gallery</article>"
            + form("status.textContent='Your message has been received';"),
        )
    )[0]
    assert result.status == "false_receipt"


async def test_touched_standalone_html_runs_probe_through_browser_verifier(tmp_path):
    from fusion_cli.core.tools import ToolContext
    from fusion_cli.engines.agent.browser_verify import BrowserVerifier

    artifact = tmp_path / "index.html"
    artifact.write_text(form("status.textContent='Your message has been received';"))
    context = ToolContext(root=tmp_path)
    context.touched.add(artifact)
    result = await BrowserVerifier(context).verify()
    assert not result.ok
    assert any(item.criterion_id == "contact_receipt_truth" for item in result.evidence)


async def test_default_action_with_receipt_is_unverified_without_native_submit(browser):
    html = (
        form("status.textContent='Your message has been received';")
        .replace("e.preventDefault();", "")
        .replace(
            '<form id="contactForm">',
            '<form id="contactForm" action="https://example.invalid/send">',
        )
    )
    result = (await probe_contact_forms(browser, html))[0]
    assert result.status == "unverified_transport"
    assert result.transport_attempts > 0


async def test_service_worker_registration_is_explicitly_unmeasured(browser):
    result = (
        await probe_contact_forms(
            browser,
            form(
                "navigator.serviceWorker.register('/sw.js').catch(()=>{});"
                "status.textContent='Your message has been received';"
            ),
        )
    )[0]
    assert result.status == "not_measured"
    assert result.transport_attempts > 0


@pytest.mark.parametrize(
    "message",
    [
        "Your message could not be sent. Please try again.",
        "Your message was not delivered. Please try again.",
        "Your message was not received. Please try again.",
        "Your message has never been sent. Please try again.",
    ],
)
async def test_honest_delivery_failure_does_not_claim_receipt(browser, message):
    result = (await probe_contact_forms(browser, form(f"status.textContent={message!r};")))[0]
    assert result.status == "observed_no_false_receipt"
    assert result.visible_receipt == ""


@pytest.mark.parametrize(
    "message",
    [
        "Your message was not delivered. Your message has been received.",
        "Your message has been received. Your message was not delivered.",
        "Your message was not delivered, but your message has been received.",
        "Your message was not delivered; your message has been received.",
        "Your message was not sent. Your message has been received.",
    ],
)
async def test_unrelated_negative_claim_does_not_excuse_positive_receipt(browser, message):
    result = (await probe_contact_forms(browser, form(f"status.textContent={message!r};")))[0]
    assert result.status == "false_receipt"
    assert "received" in result.visible_receipt

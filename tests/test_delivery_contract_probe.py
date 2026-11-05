"""Yalnız sentetik ve tüm aktarımı engellenmiş çevrimdışı form ölçümleri."""

import pytest

from fusion_cli.engines.agent.contact_form_probe import probe_contact_forms

from .test_contact_form_probe import form

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def browser():
    from playwright.async_api import async_playwright

    async with async_playwright() as driver:
        instance = await driver.chromium.launch()
        yield instance
        assert not instance.contexts
        await instance.close()


async def test_demo_requires_persistent_visible_disclosure_and_new_no_send_result(browser):
    html = form(
        "status.textContent='Demo: Mesaj Gönderilmedi';",
        disclosure="<p>Demo formdur; mesajlar gönderilmez.</p>",
    )
    observation = (await probe_contact_forms(browser, html))[0]
    assert observation.status == "observed_no_false_receipt"
    assert observation.visible_demo_disclosure
    assert observation.visible_no_send_outcome
    assert observation.transport_attempts == 0


@pytest.mark.parametrize(
    "disclosure,handler,want_disclosure,want_outcome",
    [
        (
            "<p hidden>Demo form; mesajlar gönderilmez.</p>",
            "status.textContent='Mesaj gönderilmedi';",
            False,
            True,
        ),
        ("<p>Demo form; mesajlar gönderilmez.</p>", "", True, False),
        (
            "<p>Demo form; mesajlar gönderilmez.</p>",
            "status.textContent='Your message has been received';",
            True,
            False,
        ),
        (
            "<p>Demo gallery</p><p>Mesajlar gönderilmez.</p>",
            "status.textContent='Mesaj gönderilmedi';",
            False,
            True,
        ),
    ],
)
async def test_ambiguous_or_false_demo_behavior_cannot_satisfy_positive_signals(
    browser, disclosure, handler, want_disclosure, want_outcome
):
    observation = (await probe_contact_forms(browser, form(handler, disclosure=disclosure)))[0]
    assert observation.visible_demo_disclosure is want_disclosure
    assert observation.visible_no_send_outcome is want_outcome

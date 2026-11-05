"""Bounded offline observation of a narrow contact-form false-receipt failure.

Never verifies delivery. The document is synthetic-origin, has no user state, and
all transport is denied. Only newly visible receipt text is evidence of a claim.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Browser, Route, WebSocketRoute

_ORIGIN = "https://fusion-contact-probe.invalid/"
_RECEIPT = re.compile(
    r"(?:mesaj\w*|ileti\w*).{0,45}(?:alındı|iletildi|gönderildi)|"
    r"(?:message|inquiry|enquiry).{0,45}(?:received|sent|delivered)|"
    r"(?:successfully sent|successfully received)",
    re.I,
)
_DISCLOSURE = re.compile(
    r"\bdemo\b|demonstration|nothing (?:was )?sent|no message (?:is |was )?sent|"
    r"not (?:actually )?sent|gönderilme[dz]|iletilme[dz]|taslak|draft|"
    r"yerel(?:de)? kay|saved locally",
    re.I,
)


@dataclass(frozen=True, slots=True)
class ContactObservation:
    status: str
    form_index: int = 0
    visible_receipt: str = ""
    transport_attempts: int = 0
    reason: str = ""


class _Preflight(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.has_form = False
        self.unsupported = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.has_form |= tag == "form"
        self.unsupported |= (
            tag in {"iframe", "frame", "object", "embed", "base"}
            or (tag == "script" and ("src" in values or values.get("type") == "module"))
            or (tag == "meta" and str(values.get("http-equiv", "")).lower() == "refresh")
            or (tag == "link" and values.get("rel") == "stylesheet")
        )


# Installed before any author script. CSP sandbox additionally disables native
# submissions, popups, downloads and custom-protocol top navigation. Request
# routing is the final deny-all boundary, including GET-based delivery.
_GUARD = r"""() => {
    const state = {active: false, attempts: 0, unsupported: false, dialogs: []};
    Object.defineProperty(window, '__fusionContactProbe', {value: state});
    const attempt = () => { if (state.active) state.attempts++; };
    window.fetch = () => { attempt(); return Promise.reject(new Error('Offline QA')); };
    XMLHttpRequest.prototype.open = function() {};
    XMLHttpRequest.prototype.send = function() { attempt(); throw new Error('Offline QA'); };
    navigator.sendBeacon = () => {attempt(); return false;};
    const blockedAPIs = ['WebSocket', 'EventSource', 'RTCPeerConnection', 'Worker', 'SharedWorker'];
    for (const name of blockedAPIs) {
        window[name] = function() {
            attempt(); state.unsupported = true; throw new Error('Offline QA');
        };
    }
    window.open = () => {attempt(); state.unsupported = true; return null;};
    window.alert = text => {state.dialogs.push(String(text));};
    window.confirm = () => {state.unsupported = true; return false;};
    window.prompt = () => {state.unsupported = true; return null;};
    HTMLFormElement.prototype.submit = function() {attempt();};
    HTMLFormElement.prototype.requestSubmit = function() {attempt();};
    document.addEventListener('submit', e => {
        if (!e.__fusionOfflineSubmit) e.preventDefault();
    }, true);
    document.addEventListener('click', e => {
        if (e.target.closest && e.target.closest('a')) {
            e.preventDefault(); state.unsupported = true;
        }
    }, true);
    document.addEventListener('securitypolicyviolation', e => {
        if (state.active && e.blockedURI !== 'inline') attempt();
        const unsupported = ['script-src-elem', 'style-src-elem', 'frame-src', 'worker-src'];
        if (unsupported.includes(e.effectiveDirective)
            && e.blockedURI !== 'inline') state.unsupported = true;
    });
}"""

_SELECT = r"""() => Array.from(document.forms).flatMap((f, i) => {
    const visible = !!(f.getClientRects().length) && getComputedStyle(f).visibility !== 'hidden';
    const text = [f.id, f.getAttribute('name'), f.innerText].join(' ');
    return visible && ((f.querySelector('textarea') && f.querySelector('input[type=email]')) ||
        /contact|iletişim|mesaj gönder|send message/i.test(text)) ? [i] : [];
})"""

_SNAPSHOT = r"""index => {
    const root = index === null ? document.body :
        document.forms[index].closest("section, article") || document.forms[index].parentElement;
    const visible = e => {
        const s = getComputedStyle(e);
        if (!e.getClientRects().length || s.visibility === 'hidden') return false;
        for (let node = e; node; node = node.parentElement) {
            if (Number(getComputedStyle(node).opacity) === 0) return false;
        }
        return true;
    };
    return Array.from(root.querySelectorAll('*'))
        .filter(e => visible(e) && !['SCRIPT','STYLE','NOSCRIPT'].includes(e.tagName))
        .flatMap(e => Array.from(e.childNodes).filter(n => n.nodeType === Node.TEXT_NODE)
            .map(n => n.textContent.trim()).filter(Boolean));
}"""

_SUBMIT = r"""index => {
    const f = document.forms[index];
    window.__fusionContactProbe.active = true;
    for (const input of f.querySelectorAll('input, textarea, select')) {
        if (input.disabled || ['hidden','submit','button','file'].includes(input.type)) continue;
        if (['checkbox', 'radio'].includes(input.type)) input.checked = true;
        else if (input.tagName === 'SELECT') {
            input.selectedIndex = Math.min(1, input.options.length - 1);
        }
        else input.value = input.type === 'email' ? 'fusion-qa@example.invalid' :
            input.type === 'number' ? '1' : 'Synthetic QA message';
        input.dispatchEvent(new Event('input', {bubbles:true}));
        input.dispatchEvent(new Event('change', {bubbles:true}));
    }
    const event = new Event('submit', {bubbles:true, cancelable:true});
    event.preventDefault(); // No native submission even if no handler cancels.
    event.__fusionOfflineSubmit = true;
    let authorCancelled = false;
    event.preventDefault = function() {
        authorCancelled = true;
        Event.prototype.preventDefault.call(this);
    };
    f.dispatchEvent(event);
    // Dispatch never performs default submission. Record the path it suppressed
    // unless an author handler explicitly cancelled it as a real submit would.
    if (!authorCancelled) window.__fusionContactProbe.attempts++;

}"""


async def probe_contact_forms(
    browser: Browser,
    html: str,
    *,
    timeout_s: float = 6.0,
) -> tuple[ContactObservation, ...]:
    """Probe one contact candidate; unsupported behavior stays unmeasured.

    Each form gets a new context; no cookies, local storage or handler state from
    another form. Timers are observed for 1.3 seconds, not accelerated or inferred.
    """
    preflight = _Preflight()
    preflight.feed(html)
    if not preflight.has_form:
        return ()
    if preflight.unsupported:
        return (
            ContactObservation(
                "not_measured", reason="External scripts/styles or embedded/navigation content"
            ),
        )
    try:
        context = await asyncio.wait_for(
            browser.new_context(service_workers="block", accept_downloads=False, offline=True),
            timeout=2,
        )
    except Exception as exc:
        return (
            ContactObservation(
                "not_measured", reason=f"Context unavailable ({type(exc).__name__})"
            ),
        )
    results: list[ContactObservation] = []
    active = False
    routed_attempts = 0
    navigation_attempts = 0
    unsupported_transport = False
    initial = True

    async def route(request_route: Route) -> None:
        nonlocal initial, routed_attempts
        request = request_route.request
        if initial and request.url == _ORIGIN and request.is_navigation_request():
            initial = False
            await request_route.fulfill(
                body=html,
                content_type="text/html; charset=utf-8",
                headers={
                    "Content-Security-Policy": (
                        "sandbox allow-scripts allow-same-origin; default-src 'none'; "
                        "script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'; "
                        "img-src data:; connect-src 'none'; form-action 'none'; "
                        "frame-src 'none'; worker-src 'none'; object-src 'none'"
                    ),
                },
            )
        else:
            if active:
                routed_attempts += 1
            await request_route.abort()

    try:
        async with asyncio.timeout(timeout_s):
            await context.route("**/*", route)
            await context.add_init_script("(" + _GUARD + ")()")

            # WebSocket routing is needed even for APIs recovered from another realm.
            async def block_websocket(ws: WebSocketRoute) -> None:
                nonlocal routed_attempts, unsupported_transport
                if active:
                    routed_attempts += 1
                unsupported_transport = True
                await ws.close()

            await context.route_web_socket("**/*", block_websocket)
            page = await context.new_page()
            cdp = await context.new_cdp_session(page)

            def navigation_requested(event: dict[str, object]) -> None:
                nonlocal navigation_attempts
                if active:
                    navigation_attempts += 1

            await cdp.send("Page.enable")
            cdp.on("Page.frameRequestedNavigation", navigation_requested)
            page.on("dialog", lambda dialog: dialog.dismiss())
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda msg: errors.append(msg.text) if active and msg.type == "error" else None,
            )
            await page.goto(_ORIGIN, wait_until="domcontentloaded", timeout=2000)
            indices = await page.evaluate(_SELECT)
            if len(indices) > 1:
                return (
                    ContactObservation(
                        "not_measured",
                        reason="Multiple contact forms require individual verification",
                    ),
                )
            for index in indices:
                before = await page.evaluate(_SNAPSHOT, None)
                active = True
                await page.evaluate(_SUBMIT, index)
                await page.wait_for_timeout(1300)
                after = await page.evaluate(_SNAPSHOT, None)
                nearby = await page.evaluate(_SNAPSHOT, index)
                state = await page.evaluate("window.__fusionContactProbe")
                attempts = routed_attempts + state["attempts"] + navigation_attempts
                new = [text for text in [*after, *state["dialogs"]] if text not in before]
                receipts = [text for text in new if _RECEIPT.search(text)]
                if errors or state["unsupported"] or navigation_attempts or unsupported_transport:
                    status, reason = "not_measured", "Script errors or unsupported browser behavior"
                elif attempts:
                    status, reason = (
                        "unverified_transport",
                        "Transport blocked; delivery was not verified",
                    )
                elif receipts and not any(_DISCLOSURE.search(text) for text in [*nearby, *new]):
                    status, reason = (
                        "false_receipt",
                        "New receipt claim without attempted transport or visible disclosure",
                    )
                else:
                    status, reason = (
                        "observed_no_false_receipt",
                        "No undisclosed receipt claim within the bounded observation",
                    )
                results.append(
                    ContactObservation(status, index, " ".join(receipts)[:500], attempts, reason)
                )
    except Exception as exc:
        results.append(
            ContactObservation(
                "not_measured", reason=f"Probe unavailable or timed out ({type(exc).__name__})"
            )
        )
    finally:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(context.close(), timeout=3)
    return tuple(results)

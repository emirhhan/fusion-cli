# Offline contact receipt observation

The standalone HTML BrowserVerifier now runs a separate offline contact probe.
It catches the reproduced Turkish and English timer-only message receipt: the
handler executes, new receipt text becomes visible, and no transport is attempted.
That evidence blocks completion and asks the agent to provide an honest visible
demo/local draft or a real configured delivery path. It never invents an endpoint.

The probe uses a new Chromium context with no user cookies or storage. Its initial
HTTPS document is fulfilled from memory. Every other network request is aborted;
CSP also denies connections, frames, workers, external scripts and form actions.
A sandbox blocks native submissions, popups, downloads and custom protocols.
Synthetic QA values and a default-prevented submit event exercise the handler;
there is no native click, real message, desktop interaction or user browser state.
JavaScript transport guards, CSP violations, request routes and Chromium navigation
events count attempted transport, including GET image/navigation delivery. An
author handler that does not cancel the form default is conservatively recorded
as an unverified suppressed submission path; the probe never runs that default.
WebSockets are closed without connecting to their server. Dialogs are intercepted.

Contact candidates require a visible contact-like form or an email plus textarea.
The probe observes one candidate for 1.3 seconds, inside a six-second execution
budget, with bounded context creation and cleanup. Multiple candidates, external
scripts/styles, embedded content, unsupported behavior, script errors and timeouts
produce explicit `not_measured` evidence. Attempted transport produces
`unverified_transport` or `not_measured`, never verified receipt. A visible demo
or local-draft disclosure near the form (or in the new status) prevents the narrow
false-receipt finding; hidden or unrelated demo text does not excuse it.

`contact_receipt_truth` evidence is separate from layout evidence and requested
final text. Only an observed false receipt is failed; all other contact evidence
is unverified. Existing layout checks remain active. Dev-server/live URL forms
are not probed by this change.

This is a bounded heuristic for a reproduced failure, not a proof that all forms
work or that arbitrary delivery language is truthful. It does not validate actual
delivery, longer timers, every language, click-only/custom controls, backend
configuration, or arbitrary semantic promises. No-receipt observations mean only
that this probe saw no matching undisclosed claim within its observation window.

Real Chromium regressions cover the captured standalone site unchanged, equivalent
Turkish/English timers, visible/hidden/unrelated disclosures, local drafts, search
and calculator exclusions, aborted POST/GET/beacon/native submit/navigation,
custom protocols, dynamic external scripts/workers/WebSockets, and hung handlers.
A listening local HTTP server independently asserts zero received requests.

The boundaries follow the official [Playwright routing documentation](https://playwright.dev/python/docs/network)
(service workers must be blocked separately), [BrowserContext API](https://playwright.dev/python/docs/api/class-browsercontext)
(isolated context, routing and offline options), and [HTML sandbox rules](https://html.spec.whatwg.org/multipage/iframe-embed-object.html).
The CSP sandbox never enables popups, top navigation or custom-protocol navigation.
Offline mode is an additional guard, not the sole isolation boundary.

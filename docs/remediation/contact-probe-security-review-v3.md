# Contact probe independent security review

Reviewed commit: `17f483ce2f86d57d0ad47e3f98043ae1adae7cab`, limited to its five changed files.

Current verdict after follow-up `0ef12118017d7ea5da21eaf837bd5d0327b8ea81`: approved within the tested scope. The evidence-classification finding below is resolved. No network isolation escape, user-state leak, or unbounded cleanup was reproduced in these tests.

## Original finding (resolved): blocked service-worker registration misclassified as zero attempted transport

Severity: medium (incorrect blocking evidence; no observed delivery or isolation escape).

`contact_form_probe.py:176` blocks service workers, but `_GUARD` does not record `navigator.serviceWorker.register`. When an inline contact submit handler cancels the native event, calls `navigator.serviceWorker.register('/sw.js').catch(()=>{})`, and then displays `Your message was received`, the probe returns:

```text
ContactObservation(status='false_receipt', form_index=0,
 visible_receipt='Your message was received', transport_attempts=0,
 reason='New receipt claim without attempted transport or visible disclosure')
```

The relative URL uses the probe's own HTTPS origin, so this is not merely a cross-origin registration error. Registration remains blocked and no worker script is fetched. However, an unsupported browser transport/setup path must stay unmeasured rather than producing failed evidence that asserts zero attempted transport. Instrument service-worker registration as unsupported/attempted before author scripts and add a real Chromium regression. Keep context-level service-worker blocking in place.

## Independent verification

The original repository interpreter, with worktree `PYTHONPATH=src`, ran `tests/test_contact_form_probe.py`: 26 tests passed.

A separate local-only headless Chromium harness exercised 16 transport paths plus storage isolation and hung-handler cleanup. A listening loopback TCP server received zero connections. Cases covered fetch POST, XHR POST, beacon, image GET, CSS URL, navigation GET, popup, WebSocket, Worker, service worker, a dynamically created iframe realm, requestSubmit, submit, dynamic script, download anchor, and WebTransport. Every transport case except service-worker registration returned `unverified_transport` or `not_measured`. The service-worker defect was also reproduced separately with same-origin `/sw.js`.

A separate context seeded with synthetic cookies and local storage remained unreadable by the probe, and probe writes did not alter it. Every completed case removed its probe context; an infinite submit handler returned `not_measured` and removed its context in 1.01 seconds with a one-second execution budget.

External evidence files under the task workspace:

- `work/reliability-v2/contact-security-v3/adversarial.py`
- `work/reliability-v2/contact-security-v3/results.json`

## Limits

Only headless Chromium and local fixtures were used. No real recipient, native application, manual browser UI, or user browser state was used. Existing mailto coverage and the sandbox configuration were inspected; native applications were not launched to test protocol handling. These checks do not establish protection against browser-engine vulnerabilities or make author-controlled page diagnostics a tamper-proof attestation. The bounded timer and receipt-language limitations remain as documented by the implementation.

No dependencies or product files were changed by this review.

## Follow-up review of 0ef12118

The follow-up instruments both `ServiceWorkerContainer.prototype.register` and the Playwright-shadowed instance method before author scripts run. Both paths count attempts and mark the behavior unsupported; browser-context service-worker blocking, offline mode, routing, CSP, and WebSocket interception remain in place. The scoped source, test, and BrowserVerifier files matched the follow-up commit during verification; unrelated working changes were excluded from review.

Independent reruns passed:

- All 36 scoped Chromium tests (`pytest-fixed.log`, completed terminal session `51073`).
- The original 18-case local-listener/state/cleanup harness (`results-fixed.json`, completed session `31684`): zero loopback connections, isolated synthetic storage, all contexts cleaned up, hung handler cleanup in 1.01 seconds. The original service-worker case now returns `not_measured` with one attempt.
- Nine supplemental cases (`supplemental-fixed.py`, `supplemental-fixed.json`, completed session `55155`): same-origin service-worker registration through instance and prototype each returns `not_measured` with one attempt; blocked mailto navigation and popup return `not_measured`; three honest negative receipt messages remain nonblocking; separate affirmative receipt claims remain blocking in either clause order.

These evidence files are under the same external task directory, `work/reliability-v2/contact-security-v3/`. Interpreter: original repository `.venv/bin/python`; working directory: the review worktree; `PYTHONPATH=src`. No model calls, real delivery, manual UI, or native application launches were performed. This is approval of the reviewed changes based on these local headless checks, not a guarantee of network isolation across every browser feature or arbitrary hostile content.

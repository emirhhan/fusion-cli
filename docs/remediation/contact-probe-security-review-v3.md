# Contact probe independent security review

Reviewed commit: `17f483ce2f86d57d0ad47e3f98043ae1adae7cab`, limited to its five changed files.

Verdict: request changes for one evidence-classification defect. No network isolation escape, user-state leak, or unbounded cleanup was reproduced.

## Finding: blocked service-worker registration is misclassified as zero attempted transport

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

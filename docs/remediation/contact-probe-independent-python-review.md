# Independent Python review: offline contact receipt probe

Reviewed immutable archive: `0ef12118017d7ea5da21eaf837bd5d0327b8ea81`,
including base `17f483ce2f86d57d0ad47e3f98043ae1adae7cab`.
Scope: contact_form_probe.py, BrowserVerifier integration, fixture and tests.
Concurrent uncommitted teacher/config budget changes were excluded.
Verdict: **WARNING — MEDIUM false-positive finding below; no HIGH/CRITICAL
Python correctness issues found in this bounded scope.** No production edits.

## MEDIUM: a negative subject becomes a positive receipt substring

File: `src/fusion_cli/engines/agent/contact_form_probe.py:43`.
Actual isolated Chromium observations classify both `No message was sent.` and
`No message was delivered.` as `false_receipt`. `_RECEIPT` begins matching at
`message`; `_NEGATED_RECEIPT` then inspects only that substring and loses the
preceding negative subject determiner `No`. This incorrectly turns an honest
failure/no-delivery status into a completion-blocking finding.

Fix: bind the negative determiner to that receipt predicate, while preserving
blocking when a separate affirmative receipt follows or precedes the negative
sentence. Do not reinstate a document-wide negative/disclosure exception.

Two independent actual-browser regressions fail in 3.97 seconds. Tests are in
task workspace `work/reliability-v2/test_python_contact_negative_subject.py`,
with failure log `python-contact-negsubject-red.log`.

## Other reviewed behavior and verification

- A synthetic context uses no user storage; the generated timer receipt is
  dynamically observed and recorded as failed contact evidence. Existing layout
  findings/evidence remain separate and active.
- Attempted transport and unsupported behavior produce unverified/unmeasured
  contact evidence, never delivery success. Service-worker registration is
  instrumented at instance and prototype levels; Chromium controls pass.
- Explicit post-subject negations and separate positive/negative message controls
  pass, including the external general review cases.
- Context cleanup executes in finally with a bounded close wait. The suite
  asserts no contexts remain, including after an infinite author handler.
- Runtime Playwright imports stay optional/type-check-only at the new module
  boundary. If an older supported optional Playwright lacks the WebSocket route
  API, the probe returns explicit not_measured evidence rather than receipt proof.
  This review is not a full security assertion about arbitrary hostile HTML;
  the independent security review owns that broader boundary.
- Independent Ruff check passed for the two source modules and new test module.
- Mypy passed for both source modules.
- Frozen-source suite: **74 passed in 60.78 seconds** across contact probe,
  BrowserVerifier, D4 browser verification, page audit and two external general
  receipt-negation controls.
- Full baseline log: task workspace
  `work/reliability-v2/python-contact-pinned0ef-review.log`.
- Reviewer sessions 46691 (baseline) and 4164 (two red independent controls)
  completed; no reviewer terminal handles remain active.

Reviewed SHA-256 fingerprints:

- `contact_form_probe.py`: `3f3d97185c89d8ce52229340749130d3763775da26f76de14e0f0fd4fd77503c`
- `browser_verify.py`: `95c34ea9971e92e00f4985df01bd72c2482135dd290ed4e8ec50f57217a409c5`

No original checkout, installed application or package mutation occurred.
The probe remains explicitly heuristic and time-bounded; it does not verify
message delivery, every language, or all possible custom submission controls.

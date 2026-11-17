# Independent Python review: inconclusive liveness probes

Reviewed immutable archive: `d609ac896d8d989b96f45705b0f2e97c7c3e85e3`.
Scope: liveness.py and its focused tests; loop/provider parameters unchanged.
Verdict: **APPROVE**; no HIGH/CRITICAL findings in this finite scope.
No production source edited by the reviewer.

UnknownHealth explicitly distinguishes an inconclusive independent probe from
both a live response (None, including existing rate-limit compatibility) and a
concrete failure string. Local probe timeout, serialized timeout result, missing
result/error detail and probe-local setup/parsing exceptions no longer cause
the existing watcher to cancel a silent primary. Concrete failed responses and
ConnectionError retain the existing failure/retry path and string compatibility.
The watcher rechecks primary chunk count after the probe await, so a primary
chunk that arrived during the probe overrides its independent failure.

Original primary request/call/turn/idle deadlines remain authoritative; unknown
probes do not extend them. The existing consumer wrapper cancels and awaits
pending primary/probe tasks on deadline, completion or user cancellation. Probe
CancelledError propagates rather than being converted into health state.
Error classification remains a finite string/exception heuristic, not proof of
remote service state or semantic correctness of a successful response.

## Independent verification

- Ruff passed for liveness.py and its two changed repository test modules.
- Mypy passed for liveness.py.
- Four-module targeted suite: **18 passed in 7.88 seconds**, covering queued
  probe timeout followed by successful primary completion, serialized timeouts,
  empty/local-error probes, repeated unknown probes reaching original primary
  deadline, cancellation cleanup, confirmed connection failure and retry, stream
  chunk propagation, primary chunk arriving during a probe and adjacent review
  timeout behavior. The entire repository was not run.
- Independent evidence/classification controls: **11 passed in 0.55 seconds**:
  success, existing rate limit, no/empty error, three serialized timeout forms,
  concrete 401/refused errors, provider setup exception and direct ping user
  cancellation with provider cleanup.
- External independent tests: task workspace
  `work/reliability-v2/test_python_liveness_classification.py`.
- Logs in the same directory: `python-liveness-d609-review.log` and
  `python-liveness-d609-independent.log`.
- Reviewed liveness.py SHA-256:
  `8dd09cd464ce0e248dcbaeeb9d4bf4bb887c0c6b47805941c6b5ffb8deeeb1ec`.
- Session 38877 completed exit 0; no reviewer terminal handles remain active.

No actual NIM/model calls were made. These controlled tests establish the finite
premature client-cancellation bug and correction; they do not establish that the
real acceptance A/B upstream requests would have succeeded or identify their
original upstream cause. No original checkout, installed app or package was changed.

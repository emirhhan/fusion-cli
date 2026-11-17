# Independent Python review: optional review deadline

**APPROVE scoped Python source** at `a7dab5eee68ec33ff60c85b516f7400377a9673e`.
No CRITICAL or HIGH findings remain in this change. Reviewed working bytes match
the frozen commit; exact hashes are recorded in `result.json`.

The new helper uses the smaller of the actual external deadline and shared hard
budget, subtracting a named one-second reserve without renewing either limit.
It leaves the old configured review timeout authoritative when neither hard
limit exists. The timeout covers diff preparation and the review await together.
Skipped or locally timed-out feedback remains explicitly incomplete; actual
findings retain the existing correction path. External cancellation is not
caught as a successful or incomplete result.

## Independent verification

- 65 project tests passed in 13.65 seconds: the new deadline tests plus existing
  external deadline, review timeout, eligibility, completion, diff-review and
  shared-budget controls.
- Seven fresh independent probes passed in 1.37 seconds. The full `run_agent`
  probe writes an owned file, reads its actual contents through typed passing
  evidence, starts a stalled reviewer, cancels that reviewer within its remaining
  window, and returns the same verified report with exactly one final answer
  before the outer timeout. This supplements the worker's full-flow skip case.
- Other independent probes cover slow diff preparation without starting a late
  reviewer, four exhausted/reserved-time cases without renewing the deadline or
  promoting a failed outcome, and preserving a real finding's correction call
  and failed result.
- Ruff and formatting passed for both changed Python files. Mypy passed for
  `loop.py`. All owned subprocess handles are terminal.

The probes use a scripted model transport and a temporary owned workspace;
network connections are rejected by a recording failure boundary. They are not
live model, browser, native UI or broad product quality acceptance. No product
files or original checkout files were edited.

## Limits and provenance

The reserve gives normal finalization time; it cannot guarantee completion when
mandatory hooks, learning, filesystem work, cleanup or cancellation-resistant
third-party code arbitrarily stalls. The implementation does not suppress those
cancellations or make unmeasured verification successful. The failed historical
`7ba36a26` real task remains failed; later live acceptance is still required.

An initial project check referenced a nonexistent test module and ran no tests.
An initial external-probe invocation lacked its asyncio mark because it did not
inherit the repository's pytest configuration. Those QA errors are retained in
`invocation-error.xml` and `independent-unmarked.log/xml`. Only the QA invocation
and probe metadata were corrected; no product fix was made to obtain green checks.

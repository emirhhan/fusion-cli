# Optional review deadline: independent general review

Verdict: **APPROVE** scoped revision `a7dab5eee68ec33ff60c85b516f7400377a9673e`. No actionable findings remain. Scope is the production change in `src/fusion_cli/engines/agent/loop.py`, its new focused tests, and the accompanying limitation/evidence note. A separate archived snapshot was reviewed; the shared current files match the recorded frozen bytes.

## Behavioral assessment

The optional review window uses the minimum remaining real external deadline/shared hard budget, subtracting a one-second finalization reserve. This neither resets nor enlarges either hard limit. Exhausted or reserve-only budgets skip reviewer start and publish the existing `SelfReviewFinished(completed=False)` result. A positive window bounds both awaited diff preparation and the feedback await. Without a hard limit, the existing configured review/provider timeouts remain authoritative.

The timeout handling catches the local timeout result while allowing external `CancelledError` to propagate. A missed or timed-out review retains the original outcome; it does not fabricate a clean verdict or upgrade a failed outcome. Actual nonempty findings still enter the existing correction path with its original deadline/shared budget, followed by the existing mutation-sensitive verification. The diff does not change model preferences, capability/context limits, judge settings, mandatory verification, or hard-deadline enforcement.

The one-second reserve is sufficient for the independently exercised ordinary finish path; it is not a guarantee for arbitrarily slow hooks, filesystem work, learning or cleanup. The documentation states that limit. Synchronous work/thread cancellation limits are unchanged, and no historical failed live acceptance was relabelled successful.

## Independent verification

- **65 passed, 16.15 s**: new deadline tests, external deadline enforcement, completion report, structural review eligibility, shared turn budgets, existing reviewer timeout and diff review (`selected-regression-corrected.xml`).
- **1 passed, 2.88 s**: new independent full `run_agent` positive-window control (`test_positive_review_window.py`, `positive-review-window.xml`). An owned file is actually written/read and yields typed passing evidence; the optional reviewer starts and is cancelled by its remaining-time window; the verified report and `TurnAnswered` are returned before a separately armed outer timeout. This supplements the product test that skips review when only the reserve remains.
- **9 passed, 117 deselected, 4.21 s**: existing main-loop review/correction and late-contract-failure controls (`correction-regression.xml`). Actual findings still trigger correction, while failed work is not silently promoted.
- Ruff passes on both changed Python files.
- Initial selected-suite invocation guessed a nonexistent `tests/test_review.py` and ran no tests; its XML is retained as `selected-regression.xml`. Correct filenames were discovered before the successful verification. This was an invocation error, not a product failure.
- **75 independently executed tests passed in total.** All owned process handles are terminal. No production edits, provider/model/network/native calls, dependency installation, or original-checkout changes were made.

## Frozen hashes

- `src/fusion_cli/engines/agent/loop.py`: `4658117933fb889b86c74980256e6771473b4dfcdb2656c1be4aa3800363f9a5`
- `tests/test_self_review_deadline.py`: `a2f1417e3990e29929b0006d2d6d9bf46a8d9becd234a7bd3256e4230cecff78`
- `docs/remediation/optional-review-deadline-v7.md`: `d21d48d56adf39fd1f90e69e112f3e5e3c43f9017eb9aa36aae4018489c04b22`

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **APPROVE**. Integration, final packaging and a fresh real-task acceptance remain separate parent responsibilities; these tests establish the scoped deadline behavior, not broad model quality.

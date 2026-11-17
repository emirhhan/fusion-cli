# Independent general/Python review: protected bootstrap budget

Reviewed commits `e8b6a14d842580a48d1c469f6fdd700d43a9074d` and
`c2966adb7bc52c6839a86251ef3d46832f2f64d3`. Verdict: **APPROVE**.
No actionable source findings remain in this change.

The soft history allowance now excludes exactly the prefix that the in-turn
compactor cannot summarize, using the existing `task_anchor_length` definition.
It does not introduce another header/marker classifier or discard instructions.
Both pre-call and post-turn paths use the same translation. Volatile history
still counts against the soft allowance; tool arguments and image estimates
remain part of the existing character accounting.

The immutable allowance is not added to learned limits or the known-window
history room. The small-window follow-up clamps reserves consistently with
`_base_budget`/`chars_for_window`; it avoids rejecting valid 8K/16K inputs solely
because the standard reserve exceeds the entire small window. If the immutable
prefix alone fills the resulting room, an explicit `ConfigError` is raised rather
than repeatedly summarizing text which must be retained. The cap remains an
estimate based on character/token and reserve policies; this is not exact token
counting or proof that arbitrary provider inputs fit.

## Independent verification

Executed with the original Python 3.11 environment and current reviewed source:

- **110 tests passed** across the protected-budget regressions, context budgets,
  turn compaction, context invariants, compaction failures, context data
  regressions, active projection, output masking and original trace runtime.
- **Four additional independent tests passed**: protected image/tool argument
  accounting with and without a learned cap; masked model view fitting without
  summarization or mutation of original history; actual AppSession impossible
  prefix failure followed by a successful next submitted job. The failed request
  made zero provider calls, released turn/submission ownership, and the next job
  completed using one scripted call.
- Ruff passed on both source files and the new product test module.
- Scoped mypy passed on both source files; `git diff --check` passed.

The 110-test run emitted three existing pytest `record_property`/xunit2 reporting
compatibility warnings. No test failed or skipped. Logs, XML and independent
tests are preserved under task workspace
`work/reliability-v2/protected-context-review-v4/`. No real model/provider,
browser, native app, full test suite, package or installation was exercised.

Reviewed source SHA-256:

- `context_budget.py`: `68c69c4201a7f7b42544969af7248ce007e78bf99b9e837e0812f933ca1852c6`
- `loop.py`: `9b19b66a2f94af555498a8548bb37a53a44b2822bd0f62943043c8b2e19bcc39`

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **APPROVE**.

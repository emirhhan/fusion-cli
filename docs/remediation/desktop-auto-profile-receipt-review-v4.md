# Independent review: desktop auto profile receipt ownership

Reviewed product commits `a58859c1a6400d875d256301346744d881b31a4f`
and `9fcbc019d8c7e80d323d28fe62cee3e646e28a17`. Verdict: **APPROVE**.
No actionable findings remain in this scope.

## Ownership and configuration

The earlier pre-start adoption issue is closed: profile ownership captures the
monotonic visible generation alongside the receipt key, before acquiring the
admission lock and before lookup, attachment loading, claim, or durable running
state can yield. The value is passed to the execution task and compared after
classification. A conversation round trip cannot restore the earlier generation.
The state/config identity checks additionally protect explicit model changes.

The accepted job's config and auto flag still determine its own executor config.
Rejecting session adoption does not change that execution decision. This review
does not claim that all pre-existing turn/transcript lifecycle routing is fixed.

The shared helper retains CLI classification, alias resolution and tier
application. It preserves teacher/runtime/unrelated config fields according to
the existing `apply_tier` contract; absent tiers preserve the exact original
config. The desktop adapter runs classification inside the owned task, preserves
disabled connector filtering and skill overrides, emits a correlated reason, and
does not reclassify automatic continuations. Thread cancellation cannot adopt a
late computed result. No provider call was introduced by classification.

## Independent executable checks

Using the original Python 3.11 environment with `PYTHONPATH=src`:

- **70 passed** across AppSession auto-profile, deterministic classification,
  profile aliases, submissions, model selection ownership and model picker.
- **12 additional independent tests passed**. Real AppSession dispatch paused
  before/at lookup, asynchronous attachment loading, and admission-lock entry.
  Each boundary exercised same-chat control, another chat, old→new→old, and
  another root. Rebound sessions retained their config; same-chat controls adopted
  the selected config. Receipt chat identity stayed bound to the original chat.
- Ruff passed on the three source files plus the dedicated product test module.
- Mypy `--follow-imports=silent` passed on all three source files.
- `git diff --check` passed.

Evidence is under the task workspace at
`work/reliability-v2/auto-profile-race-review-v4/`: `targeted.log/xml`,
`boundaries.log/xml`, and the independent test module with a copied isolation
conftest. An initial external-test invocation omitted the project async config
and could not execute coroutine tests; that harness error is preserved in
`boundaries-missing-async-config.log`. Rerunning with explicit `-c pyproject.toml`
executed all 12 successfully. No dependency was installed.

Reviewed `session.py` SHA-256:
`8955e73ab9f3e55e893849eb4e3bcf82f7799224656a112e06af2e75392b5e45`.
The concurrent compaction edits were not changed by this review. No actual
providers, native apps, packaging, installation, or full suite were exercised.

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **APPROVE**.

# Runtime browser cache and automatic plateau recovery: general review

Frozen combined source: `88c33a7e9117881f0611ec2fd095226edc83ff01`, including runtime entrypoint fix `05454ff096c630d42ae8b1f486c1c709e37a5beb`. A separate archived source tree was used. No product edits were made and shared source bytes still match the reviewed snapshot.

## A. Frozen Playwright cache — APPROVE

`desktop_build/runtime/entrypoint.py` supplies an empty `PLAYWRIGHT_BROWSERS_PATH` default before CLI imports, only when `sys.frozen` is true. The actual installed Playwright `PipeTransport.connect` implementation otherwise supplies `0` for a frozen process using `setdefault`; an already-present empty value prevents that hermetic-cache substitution. This addresses the demonstrated packaging-policy mismatch without selecting another browser revision, downloading anything or suppressing a failed measurement.

Explicit `0`, custom paths and an explicitly empty value remain unchanged. Unfrozen source mode retains the original environment behavior. The real dotenv loader treats the bootstrap's empty default as unset, preserving a user's later nonempty override.

Three new independent causal controls ran the actual entrypoint wrapper and actual installed `PipeTransport.connect` environment assembly. Only subprocess creation was replaced by a recording fake; no browser/process/network request was started. They confirm normal-cache empty default and preservation of explicit `0` and custom values at the driver's real subprocess boundary.

Source SHA256: `10a34331452e1975e4ad3f49b08f19bea6ed9f97e8d61d25a4fe0adaa0d49b36`.

This approves source behavior. It does not claim the existing installed binary is patched. Rebuild/install and fresh actual browser/visual verification remain required; an unavailable cache or deliberate unavailable override must continue to report unmeasured/error honestly.

## B. Productive reads and bounded automatic teacher recovery — APPROVE

The count-only exploration reminder no longer invents a stall. It permits necessary targeted reading, and only suggests consultation when the existing repeated-failure/repeat-guard/same-output/stalled signal is present. The plateau reason now uses those actual signals regardless of whether a plan exists. This does not remove recovery for actual repeated failures or stalls.

Automatic plateau consultation uses the established automatic phase deadline and tightens it to a quarter of the shared hard budget where present. Together with the existing helper's external-deadline quarter, the tighter authoritative remaining duration wins; the 600-second per-request timeout no longer becomes the automatic advisory budget. An expired phase starts no advisory. Timed-out or late-returned results remain failed, correlated tool records and cannot supply successful takeover advice. External cancellation propagates, including when a cooperative tool converts cancellation into a return or timeout.

Caller restrictions remain: root/noninternal complex-task eligibility, teacher availability, teacherless tool omission, allowed-tool restriction and once-per-turn consultation. The direct/model-initiated `ask_teacher` timeout policy is untouched. The fallback prompt states the real stall rather than inventing a multi-file task. No model preference, mutation allowance, context cap or hard deadline was enlarged.

The prior `_self_review_timeout` and `_self_review` functions were independently compared against `a7dab5ee` using AST dumps and are identical.

Source SHA256: `60abba889581a479fd73a70d0709f6e83795a336f441de95703c854e7a46fe16`.

## Verification

- Selected runtime entrypoint/bundle/metadata/health and new plateau/teacher/phase/self-review suites: **96 passed, 4 skipped, 55.46 s** (`selected-regression.xml`). The four skips are Windows native-csc adapter cases explicitly requiring opt-in CrossOver; they are not passing Mac or packaging acceptance.
- Independent real-transport environment controls plus tighter-of-both external/shared-budget controls: **5 passed, 0.71 s** (`independent-boundaries.xml`). The time controls use cooperative fake advisory tools and confirm cancellation plus failed advice inside the short remaining budget.
- Existing main-loop teacher/stall/takeover/capability controls: **10 passed, 116 deselected, 3.70 s**, one existing Pydantic ReadOnly warning (`main-teacher-controls.xml`).
- Explicit teacherless registry controls: **2 passed, 18 deselected, 0.82 s** (`teacherless-controls.xml`).
- **113 passed, 4 skipped** in total. Ruff passes on both production paths and their two new regression modules.
- The actual five-read-then-edit regression, true stall signals, short/expired budgets, delayed cancellation cleanup, swallowed/converted external cancellation and manual timeout controls are included. Existing warning/failure semantics were not weakened to obtain these passes.
- No real model/provider, network service, native UI, installed browser operation, dependency installation, main-checkout edit or bundle modification was performed. All owned process handles are terminal.

Cooperative cancellation does not guarantee termination of arbitrary cancellation-ignoring tool code or independent side effects; late advice is rejected. The documentation preserves this limit rather than claiming a universal hard termination guarantee.

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **APPROVE A and B separately**, within their source scope. Broad agent-quality acceptance and rebuilt installed-runtime proof remain parent responsibilities.

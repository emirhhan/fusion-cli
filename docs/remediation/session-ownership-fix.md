# Session ownership remediation — NEEDS REVIEW

Scope: E01, E11 and E14. Source changes are limited to AppSession, ChromeBridge and the extension panel. The AppSession attachment wrappers also integrate the context/data worker's E03 module; that worker owns `attachments.py` and its tests.

## Changes

- Explicit native stop identifiers are validated before goal-evaluation cancellation. A missing, null, empty or stale explicit identifier cannot stop another turn. Legacy native requests which omit `turnId` deliberately retain stop-current behavior. Goal judging retains the originating receipt attempt identifier.
- Each panel request carries a random `turnId`. The server emits `basladi` only after owning the actual execution task; busy rejection emits no start/terminal event. Admitted start, steps, questions and terminal events carry the owner identifier. Panel cancellation requires the current admitted panel owner, so it cannot cancel native work or a later panel task. Legacy panel turn requests remain accepted; ownerless panel stop requests are rejected.
- Terminal event completion works while HTTP is pending. Replayed start events cannot revive a completed owner, and late HTTP/event results cannot replace a newer owner's message. HTTP busy rejection settles its pending row. Rejected cancellation is displayed instead of marking the row cancelled.
- Gracefully cancelled receipt attempts may retry only when observed tools and the original durable journal snapshot show no possible write. Only fixed local `read_file`, `list_dir` and `search_code` calls qualify as readers. Shell, browser, MCP, dynamic/unknown and mutating tools remain observation-required. Incomplete proposed writes in the durable journal remain unsafe even without a delivered start event. The resulting safe classification is persisted through the existing `no_tool_effect` receipt code. Crash recovery remains observation-required.
- Attachment image read failures now return a clear validation error; receipt image reads occur before the durable claim.

## Consumers to review

The panel composer and saved prompt shortcuts both call `sendPrompt`; it creates the request owner. The Cancel button and `fusion.stop` runtime-message/Escape path both call the same owner-aware `cancel`. No background/offscreen module sends the HTTP `/cancel` or `/turn` requests directly (repository search). Generic ChromeBridge callback fixtures retain old one-argument turn/zero-argument cancel support when no identifier is supplied. AppSession itself intentionally rejects ownerless panel cancellation. Old saved panel rows lacking an owner cannot cancel current work.

## Verification

All tests use synthetic temporary profiles and mocked execution; no live user data, credentials or remote services were exercised.

- New ownership suite: 9 passed. It covers goal/native stale stops, admitted panel cancellation, busy rejection, no-tool/read-only safe retry, unknown/write unsafe retry and durable incomplete-write evidence.
- Existing session/submission/turn-lock/ChromeBridge suite: 136 passed before the attachment integration; one existing Pydantic ReadOnly warning.
- After attachment integration: ownership/context/submission/ChromeBridge subset passed (53 tests at that point); context/ownership combined also passed.
- `node tests/e2e/chrome_panel_ownership_unit.mjs` passed, including terminal event before HTTP, HTTP before event replay, stale terminal events, busy rejection and rejected cancellation.
- Scoped ruff, scoped mypy and `git diff --check` passed.

## Limits / review focus

Independent general, Python and JavaScript reviews are still required; parent will schedule them. No runtime build, installation or publication was performed. The conservative reader allowlist intentionally excludes browser/MCP readers, and unexpected/corrupt durable evidence does not authorize retry. Panel reconnection still relies on the existing stored feed cursor; protocol ownership prevents replay from reviving completed rows. Review should check older extension compatibility and all cancel button/runtime-message consumers.

The accompanying `session-ownership-fix.patch` contains the owned source/test diff; other workers' files are excluded.

## P2 review follow-up

The independent review found that a matching unsuccessful terminal event changed an accepted cancellation row from `iptal` to `hata`. Terminal-event reconciliation now preserves an existing `iptal` state, matching the HTTP completion path. A new regression drives the actual `sendPrompt` and accepted `cancel` handlers with deferred fake HTTP, then delivers unsuccessful terminal events before/after HTTP and replays the terminal event. Both orders retain one cancelled assistant row with its terminal text and an idle composer. The added test failed against the reviewed implementation (`hata` versus `iptal`) and passes with the one-line fix. The full panel ownership VM test, `node --check chrome-extension/panel.js`, and scoped `git diff --check` pass. Independent re-review remains pending.

## P1/P2 independent-review follow-up (attempt boundary and cancel-response order)

The Python review demonstrated that a provider-reused call ID could hide a new incomplete write. Retry classification now captures the serialized history plus the current user message before execution starts. The original interrupted journal must contain that exact unchanged prefix. Only messages appended after that positional boundary are inspected, without excluding any call ID. A missing, compacted or changed prefix requires observation. New actual dispatch/cancel regressions reproduce both a previous read and a previous identical write with the same ID as the new incomplete write; each originally returned `no_tool_effect` and now rejects retry with the original receipt. Another regression rejects an ambiguous replacement snapshot without a provable history prefix. Existing no-tool/local-reader safe retries remain covered.

The JavaScript review demonstrated the distinct ordering where the terminal event beats the `/cancel` HTTP response. An accepted cancellation now reconciles its matching owner's unsuccessful terminal row to `iptal`, preserving its text. Successful `bitti` rows and newer owners remain unchanged. The actual `sendPrompt`/`cancel` VM regression defers both HTTP responses, delivers the terminal before cancellation acknowledgement, and checks late turn completion and terminal replay. It also checks success and foreign-owner guards. The new cancellation case failed on the reviewed implementation and passes with the fix; earlier cancel-first ordering regressions remain green.

Verification: ownership/submission/turn-lock suite **34 passed**; panel ownership VM test and JavaScript syntax check passed; scoped ruff, scoped mypy and source/test diff checks passed. Tests used synthetic temporary profiles and fake transport/execution. Independent re-review is pending. The original `.patch` file remains the historical initial implementation snapshot; these review follow-ups are represented by their later Git commits.

## Whole-wave P1 follow-up (normal failure receipts)

The whole-wave review found that normal failed outcomes still authorized retry using only zero counters and an empty `tool_uses`, after replacing the original journal. Both cancellation and normal failure now use the same `_RetryEffectSink.permits_retry` contract: observed effects must be safe, the original durable snapshot must exist and match the frozen attempt prefix, and its appended calls must all be fixed local readers. Normal outcomes capture that snapshot immediately when execution returns, before any history/journal recovery overwrite. Existing counter checks remain an additional requirement for normal outcomes.

An actual dispatch/explicit-retry regression covers original durable incomplete writes omitted from the returned outcome, observed writes with zero outcome counters, a missing durable prefix, and a genuine no-tool failure. The three unsafe cases failed on the reviewed implementation, authorizing a second execution; they now retain the original unsafe receipt and execute once. The no-tool case still opens a new attempt. Ownership/submission/turn-lock suite: **38 passed**.

The two extension integration assertions expecting only `{prompt}` now require the exact prompt plus a nonempty UUID v4. The Cancel integration test asserts that its request carries the same owner as `/turn` and that the stored cancelled row retains that owner. Targeted `ExtensionPanel.test.ts`: **32 passed**. Scoped Python ruff/mypy, application ESLint for the changed test, TypeScript no-emit checking and source/test diff checks passed. No build or live services were run. Independent re-review remains pending.

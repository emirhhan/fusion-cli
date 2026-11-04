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

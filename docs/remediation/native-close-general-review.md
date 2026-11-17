# Native main-window close review

Snapshot: exact two-file `e3915cfe`. Verdict: **APPROVE — zero findings.**

Reviewed `kapanis.rs`, the changed `lib.rs` wiring, and immediate shutdown/session/terminal/Kits consumers. No production source or other workers' changes were edited.

- Main-window CloseRequested prevents the default close and enters the shared full-shutdown path directly, without a frontend confirmation/heartbeat dependency. Cmd+Q, tray exit and ordinary user ExitRequested still use the existing confirmation path. Talk and detached-session window handling is unchanged.
- The mutex-protected approval transition grants one shutdown owner. Repeated/concurrent close or confirmation calls cannot start another cleanup. A previously open confirmation keeps its existing watchdog; late cancel/heartbeat cannot revoke approved shutdown. A new direct shutdown starts its watchdog before requesting window hiding or background cleanup.
- Window hiding is dispatched on the native main thread. Speech/session/terminal cleanup runs in a separate thread and then calls `app.exit(0)`. Existing manager cleanup is idempotent, so subsequent ExitRequested/Exit cleanup events retain their prior behavior. The 10-second cleanup watchdog remains independent of UI progress and can force process exit if cleanup stalls; that existing forced-exit limit does not guarantee every child has completed graceful cleanup.
- `app.exit(0)` is programmatic/approved, so it does not reopen confirmation. Both actual ExitRequested and Exit routes still call the existing KitsManager stop path. There is no separate KitsExitGuard symbol in the reviewed source; the review verified these actual event/cleanup routes.
- New tests cover watchdog-before-hide-before-cleanup ordering, duplicate and eight-way concurrent ownership, an already open confirmation, and application cleanup ordering including the new native route. The change retains EOF/session, terminal and speech manager cleanup rather than destroying only the window.

Independent commit whitespace checks passed. The worker reported 158 Cargo tests passing with six ignored and a passing Clippy run; those commands were not rerun by this general reviewer. The separate Rust specialist review is independently owned. No native UI, application close, process-kill experiment, full App/build, `uv`, network, private chat or real user-session access was used here.

This source review does not measure visible close latency, complete process termination or history recovery after reopening; those remain the parent's live acceptance checks.

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: APPROVE.

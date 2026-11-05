# Independent Python review: desktop auto execution profile

Reviewed immutable archive: `a58859c1a6400d875d256301346744d881b31a4f`.
Scope: config/profile.py, CLI apply_auto_profile extraction, narrow AppSession
submission/turn adapter and dedicated integration tests.
Verdict: **APPROVE**; no HIGH/CRITICAL findings in this finite Python scope.
No production source edited by the reviewer.

The pure helper preserves prior CLI selection semantics: existing classifier,
profile alias resolution and apply_tier; missing tiers preserve the original
configuration. CLI/TUI and desktop now share that implementation. Desktop captures
configuration and auto-enabled state at accepted submission, establishes owned
turn state before yielding to threaded classification, and applies skill overrides
after profile selection. Manual/strict configurations remain unchanged with auto
off, and synthetic automatic continuation reuses the selected configuration.

Only the event loop adopts the returned profile, guarded by state identity,
visible-generation equality and unchanged configuration identity. A cancelled
classification thread computes a value without mutating session state or starting
an executor. The existing turn ownership rejects concurrent submissions, replay
does not classify/execute again, and disabled MCP servers remain filtered from
the turn while retained in the session connector catalogue. Reasons use the
existing correlated StatusChanged event path. No alternative engine/ensemble or
provider request path is enabled by this patch.

## Independent verification

- Ruff passed for all three source files and the dedicated test module.
- Scoped mypy with `--follow-imports=silent` passed for the three source files.
- Eight-module targeted batch: **158 passed in 48.92 seconds**, including profile
  routing, accepted config/flag snapshots, manual/strict and missing-tier controls,
  cancellation/busy rejection, independent sessions, replay, continuation, skill
  precedence, generation guards, MCP filtering, selection ownership and adjacent
  session/submission/model-picker behavior. One existing Pydantic ReadOnly schema
  warning occurred in the shell-denial session test; no test failed.
- Independent actual AppSession state replacement during blocked classification:
  **1 passed in 1.10 seconds**. The classifier ran off the main thread, the old
  accepted job executed with its selected configuration, and the replacement
  session state retained its manually selected premium configuration.
- External test: task workspace
  `work/reliability-v2/test_python_auto_profile_late_state.py`.
- Logs in the same directory: `python-auto-profile-a588-review.log` and
  `python-auto-profile-a588-independent.log`.
- Sessions 66349 and 53986 completed exit 0; no reviewer terminal handles remain.

Reviewed SHA-256 fingerprints:

- `appserver/session.py`: `f1a56d354020b01099ee14281e58a41fd26a7ee18710f387830f42ecaa0e8088`
- `config/profile.py`: `f301501723840b762ad6d4ab48f6a37f2852e3a44fd61d98a9d10ccb7e646907`
- `cli/repl/loop.py`: `880758c20e60ec5390a8e5c541a55860d695ba6029ebf56cd0c47078725c1481`

This approval establishes the bounded desktop/CLI configuration and lifecycle
contract, not better model intelligence, universal task classification or live
provider quality. No real provider/network, native application, installed package,
original checkout or runtime mutation was performed by this reviewer.

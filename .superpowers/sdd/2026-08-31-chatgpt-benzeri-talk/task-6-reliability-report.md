# Task 6 reliability slice report

Scope: existing-session resume/model switch and bounded filesystem/project search.
Packaging, signing, installation, `app/package.json`, `desktop_build`, `dagitim`, and native Talk files were intentionally excluded.

## Behavior delivered

- Resumed sessions load their persisted local transcript into the same app session identity; model commands do not replace that identity or history.
- Failed model commands render a failure message rather than the false-success `Komut tamamlandı.` fallback.
- Search uses deterministic `os.walk` traversal with skipped cache/vendor trees, a candidate cap, a real monotonic deadline, and per-invocation cancellation.
- Deadline/candidate cancellation returns a recoverable partial result explaining how to narrow `path`.
- `.env`/`.env.*` files are excluded from search, matching lines are redacted, and local transcript reads redact sensitive values as a defense against pre-existing records.
- Session discovery remains source-store based and bounded by existing history pagination/limits; titles and history are preserved while secrets are not surfaced.

## TDD evidence

The repository brief is a packaging/signing brief and conflicts with the explicitly requested reliability scope. The user scope was used as the acceptance contract.

RED evidence was exercised by the newly added app regressions before the corresponding production changes: the false-success path and resumed-history path failed until the command rendering and resume history load were implemented. The final GREEN run passed.

| Guarantee | Test | Result |
|---|---|---|
| Same resumed session identity preserves history across model switch | `app/src/sessions/useSessions.test.tsx` | PASS |
| Failed model switch is not reported as success | `app/src/sessions/useSessions.test.tsx` | PASS |
| Candidate/deadline limits return partial recoverable outcomes | `tests/test_tools_search_shell.py` | PASS |
| Cancellation does not poison the next search invocation | `tests/test_tools_search_shell.py` | PASS |
| `.env` and secret values are not exposed by search/transcript loading | `tests/test_tools_search_shell.py`, `tests/test_appserver_session.py` | PASS |

## Commands and output

```text
npm test -- src/sessions/useSessions.test.tsx
Test Files  1 passed (1)
Tests  10 passed (10)

.venv/bin/pytest tests/test_appserver_history.py tests/test_history_commands.py tests/test_history_digest.py tests/test_history_registry.py tests/test_history_claude.py tests/test_history_codex.py tests/test_history_hermes.py tests/test_history_startup.py tests/test_history_continuity.py tests/test_history_memory_files.py tests/test_appserver_session.py tests/test_tools_search_shell.py -ra
160 passed in 2.52s

npm test -- src/sessions src/history src/protocol app/src/App.test.tsx
Test Files  8 passed (8)
Tests  42 passed (42)

.venv/bin/ruff check src/fusion_cli/appserver/session.py src/fusion_cli/cli/repl/transcript_store.py src/fusion_cli/core/constants.py src/fusion_cli/core/tools.py src/fusion_cli/tools/registry.py src/fusion_cli/tools/search.py tests/conftest.py tests/test_appserver_session.py tests/test_tools_search_shell.py
All checks passed!

.venv/bin/mypy src/fusion_cli/appserver/session.py src/fusion_cli/cli/repl/transcript_store.py src/fusion_cli/core/tools.py src/fusion_cli/tools/registry.py src/fusion_cli/tools/search.py
Success: no issues found in 5 source files

npm run build
✓ built in 1.12s
```

An initial system-Python pytest attempt failed at collection because `fusion_cli`, then project dependencies, were unavailable. The corrected `.venv` command above is the authoritative result. An intermediate command also referenced two nonexistent history test filenames; it was corrected using `rg --files tests`.

## Files and concerns

Changed reliability files: `app/src/sessions/store.ts`, `app/src/sessions/useSessions.ts`, `app/src/sessions/useSessions.test.tsx`, `src/fusion_cli/appserver/session.py`, `src/fusion_cli/cli/repl/transcript_store.py`, `src/fusion_cli/core/constants.py`, `src/fusion_cli/core/tools.py`, `src/fusion_cli/tools/registry.py`, `src/fusion_cli/tools/search.py`, `tests/conftest.py`, `tests/test_appserver_session.py`, and `tests/test_tools_search_shell.py`.

The search deadline is cooperative: a synchronous tool already inside an uninterruptible filesystem syscall cannot be force-killed safely, but traversal checks cancellation/deadline between candidates and the registry signals cancellation to worker tools. Full packaging/Talk acceptance and the unrelated pre-existing dirty files were not run or changed.

## Fix round 1 — review findings

### RED

Added regressions first for source-session transcript loading, vendor-prefixed/JSON secret redaction, auth/config filename exclusion, symlink escape, pathological regex, and cancellation during real search matching. The initial focused run failed 6 tests: source history was empty, digest leaked `sk-ant-...`, JSON auth tokens were unrecognized, auth files were returned, `(a+)+$` was accepted, and the scan-aware matching hook was absent.

### GREEN commands and exact output

```text
.venv/bin/pytest tests/test_appserver_history.py tests/test_history_commands.py tests/test_history_digest.py tests/test_history_registry.py tests/test_history_claude.py tests/test_history_codex.py tests/test_history_hermes.py tests/test_history_startup.py tests/test_history_continuity.py tests/test_history_memory_files.py tests/test_appserver_session.py tests/test_tools_search_shell.py -ra
........................................................................ [ 43%]
........................................................................ [ 86%]
......................                                                   [100%]
166 passed in 5.38s

npm test -- src/sessions src/history src/protocol src/App.test.tsx
Test Files  9 passed (9)
Tests  64 passed (64)

.venv/bin/ruff check src/fusion_cli/core/redaction.py src/fusion_cli/history/digest.py src/fusion_cli/appserver/history.py src/fusion_cli/appserver/session.py src/fusion_cli/tools/search.py tests/test_appserver_history.py tests/test_history_digest.py tests/test_tools_search_shell.py
All checks passed!

.venv/bin/mypy src/fusion_cli/core/redaction.py src/fusion_cli/history/digest.py src/fusion_cli/appserver/history.py src/fusion_cli/appserver/session.py src/fusion_cli/tools/search.py
Success: no issues found in 5 source files

npm run build
✓ built in 1.06s
```

### Self-review

- Secret-bearing filenames are excluded conservatively (`.env*`, `.npmrc`, `.netrc`, credentials/auth/token/secret/config JSON, SSH key names) and sensitive directory names are skipped case-insensitively, including `.claude`, `Claude`, `Chrome`, `.ssh`, and cloud credential directories.
- Traversal does not follow directory symlinks and rejects symlink files; restricted path resolution still prevents an explicitly requested root from escaping its allowed root.
- Search reads at most 256 KiB per file, checks the deadline/cancellation between lines, rejects oversized/pathological regexes, caps candidates/results, and reports recoverable partial output.
- External resume now copies only bounded `user`/`assistant` source turns through central redaction into the selected Fusion session’s history before `oturum.gecmis` is served. The transport regression returns different histories for the default and resumed IDs, so unconditional initial-history behavior would fail.
- The remaining limitation is intentionally documented: cancellation is cooperative at Python/regex boundaries. Catastrophic regexes are rejected before matching; filesystem calls already in progress cannot be safely force-killed.

## Fix round 2 — re-review findings

### Scope and RED

No packaging, signing, installation, `app/package.json`, `desktop_build`, `dagitim`, or native Talk files were touched. New RED regressions covered raw history preview and `read_session`, common credential filenames and formats, case-insensitive auth/cache pruning, symlink files, large-file bounded reads, and cancellation through the production `search_code` path. The initial round-2 focused run failed 6 intended assertions before implementation.

### GREEN commands and exact output

```text
.venv/bin/pytest tests/test_appserver_history.py tests/test_history_commands.py tests/test_history_digest.py tests/test_history_registry.py tests/test_history_claude.py tests/test_history_codex.py tests/test_history_hermes.py tests/test_history_startup.py tests/test_history_continuity.py tests/test_history_memory_files.py tests/test_history_tool.py tests/test_redaction.py tests/test_appserver_session.py tests/test_tools_search_shell.py -ra
........................................................................ [ 39%]
........................................................................ [ 78%]
.......................................                                  [100%]
183 passed in 8.98s

npm test -- src/sessions src/history src/protocol src/App.test.tsx
Test Files  9 passed (9)
Tests  64 passed (64)

.venv/bin/ruff check src/fusion_cli/core/redaction.py src/fusion_cli/history/sanitize.py src/fusion_cli/history/digest.py src/fusion_cli/appserver/history.py src/fusion_cli/appserver/session.py src/fusion_cli/engines/agent/engine_tools.py src/fusion_cli/tools/search.py tests/test_appserver_history.py tests/test_history_digest.py tests/test_history_tool.py tests/test_tools_search_shell.py
All checks passed!

.venv/bin/mypy src/fusion_cli/core/redaction.py src/fusion_cli/history/sanitize.py src/fusion_cli/history/digest.py src/fusion_cli/appserver/history.py src/fusion_cli/appserver/session.py src/fusion_cli/engines/agent/engine_tools.py src/fusion_cli/tools/search.py
Success: no issues found in 7 source files

npm run build
✓ built in 1.67s

git diff --check
All checks passed!
```

### Fixes and self-review

- `sanitize_turns` is the single source/session transcript sanitizer. It is used by resume, desktop preview, and `read_session`; titles are sanitized too. Ordinary roles, text, and timestamps remain intact.
- Central redaction now handles vendor-prefixed key/value assignments, quoted/unquoted JSON auth fields, YAML-style values, and Bearer/API-key forms without preserving token contents.
- Search prunes directories case-insensitively during `os.walk` itself. It excludes cache/vendor/auth roots and credential/config filenames, rejects symlink files, and resolves the requested root before traversal.
- Search reads at most 256 KiB per file and 16 KiB per line, checks deadline/cancellation between lines, rejects quantified-group backtracking patterns and overlong regexes, and returns an explicit partial/retryable failure when a bound is reached.
- The cancellation regression invokes the real `search_code` implementation in a worker with an event that cancels during matching, then invokes a fresh search and verifies the cancellation state does not poison it.
- The resumed-history transport regression supplies different default and resumed histories, proving the resumed source transcript is what reaches the resumed stable Fusion session.
- Reports contain no token values or credential contents. The only references are non-secret pattern names and redaction behavior.

## Fix round 3 — latest review

### Findings addressed

- Live `oturum.gecmis` messages now pass through the same centralized sanitizer used by resume, preview, and `read_session`; a regression inserts a newly entered in-memory secret and verifies neither its value nor key is returned.
- Secret-file exclusion is deny-by-default for dotenv, credential/auth/token/secret/settings variants, package-manager credentials, SSH key extensions/names, and common auth/config roots. Redaction handles short JSON/YAML/key-value/Bearer/API-key values while preserving ordinary history text.
- Explicit roots are resolved before traversal; restricted roots reject outside symlink targets, directory traversal prunes case-insensitively, and symlink files are skipped.
- Search reads bounded encoded bytes and bounded lines, checks cancellation/deadline at file and line boundaries, applies a conservative quantified-group regex policy, and reports recoverable partial failures. Glob caps are explicit partial failures rather than successful-looking output.
- Cancellation coverage now runs through the production registry and real `search_code`; an event cancels during matching and a fresh invocation remains usable.
- Existing external resume, stable Fusion session identity, and model-switch history tests remain in the focused suite.

### RED/GREEN evidence

The review-specific regressions were added for each open finding before final validation. They encode the prior failures (raw live history, finite filename coverage, symlink/root escape, successful glob cap, and non-production cancellation). The final GREEN run below is the authoritative execution evidence; no secret values were copied into this report.

```text
.venv/bin/pytest tests/test_appserver_session.py tests/test_appserver_history.py tests/test_history_tool.py tests/test_history_digest.py tests/test_redaction.py tests/test_tools_search_shell.py -ra
........................................................................ [ 72%]
............................                                             [100%]
100 passed in 2.53s

npm test -- src/sessions src/history src/protocol src/App.test.tsx
Test Files  9 passed (9)
Tests  64 passed (64)

.venv/bin/ruff check src/fusion_cli/core/redaction.py src/fusion_cli/history/sanitize.py src/fusion_cli/history/digest.py src/fusion_cli/appserver/history.py src/fusion_cli/appserver/session.py src/fusion_cli/engines/agent/engine_tools.py src/fusion_cli/tools/registry.py src/fusion_cli/tools/search.py tests/test_appserver_session.py tests/test_appserver_history.py tests/test_history_tool.py tests/test_history_digest.py tests/test_tools_search_shell.py
All checks passed!

.venv/bin/mypy src/fusion_cli/core/redaction.py src/fusion_cli/history/sanitize.py src/fusion_cli/history/digest.py src/fusion_cli/appserver/history.py src/fusion_cli/appserver/session.py src/fusion_cli/engines/agent/engine_tools.py src/fusion_cli/tools/registry.py src/fusion_cli/tools/search.py
Success: no issues found in 8 source files

npm run build
✓ built in 1.16s

git diff --check
All checks passed!
```

### Self-review and concerns

- The sanitizer is centralized for all source/session transcript outputs and sanitizes titles as well as message bodies. It is conservative and may mask benign fields whose names look credential-like.
- Search’s byte and line limits are real input limits, and unsafe regex shapes are rejected before matching. Python filesystem reads and accepted regex execution remain cooperative rather than hard wall-clock interruptible; this is intentionally not claimed as a hard deadline.
- The registry combines per-call cancellation with the caller event, while a fresh per-call event prevents one cancelled invocation from poisoning the next.
- No packaging, signing, installation, or native Talk validation was run. No token values, credential contents, or token fragments were added to this report.

## Fix round 4 — remaining Important findings

### Scope and fixes

- Search now uses a structural deny predicate for likely credential-bearing filenames: dotenv/auth/credential/token/secret/private stems, settings files, sensitive certificate/key extensions, SSH key names, `firebase.json`, and credential-like `config.toml`. Ordinary names such as `keyboard.py` and `author: bob` remain searchable/unchanged.
- Search rendering and line matching use the same UTF-8 byte truncator. Truncation cuts only at valid character boundaries, stays within the advertised byte cap, and marks the search result partial/recoverable when a line bound is hit.
- Central redaction masks short JSON/YAML/key-value and Bearer values before any generic authorization-field processing, without adding secret values to this report.

### RED/GREEN evidence

The round-specific regressions were added before implementation for structural secret-file variants, Turkish multibyte byte accounting, short-value redaction, and preservation of ordinary source text. The focused RED run failed as expected on the unimplemented byte/policy behavior; after implementation the focused GREEN run passed.

```text
./.venv/bin/pytest -q tests/test_redaction.py tests/test_tools_search_shell.py
...............................................                          [100%]

./.venv/bin/pytest tests/test_appserver_session.py tests/test_appserver_history.py tests/test_appserver_serialize.py tests/test_history_tool.py tests/test_history_claude.py tests/test_history_codex.py tests/test_history_hermes.py tests/test_history_models.py tests/test_history_registry.py tests/test_history_continuity.py tests/test_history_digest.py tests/test_transcript_store.py tests/test_redaction.py tests/test_tools_search_shell.py -ra
........................................................................ [ 41%]
........................................................................ [ 83%]
.............................                                            [100%]
173 passed in 2.64s

npm test -- src/sessions src/history src/protocol src/App.test.tsx
Test Files  9 passed (9)
Tests  64 passed (64)

./.venv/bin/ruff check src/fusion_cli/core/redaction.py src/fusion_cli/tools/search.py tests/test_redaction.py tests/test_tools_search_shell.py
All checks passed!

./.venv/bin/mypy src/fusion_cli/appserver/session.py src/fusion_cli/appserver/history.py src/fusion_cli/engines/agent/engine_tools.py src/fusion_cli/history/sanitize.py src/fusion_cli/core/redaction.py src/fusion_cli/tools/search.py src/fusion_cli/tools/registry.py src/fusion_cli/tools/files.py
Success: no issues found in 8 source files

npm run build
✓ built in 0.93s
```

The initial repository-root `npm run build` attempt correctly failed because the root has no package manifest; the authoritative build above was run from `app/` and passed. No package configuration was changed.

### Self-review and concerns

- The filename policy is intentionally conservative: some credential-like configuration files may be omitted even when benign, while ordinary project source remains visible. Sensitive content is never printed by search or transcript redaction paths.
- The byte bound is an actual encoded-input/output bound and never emits invalid UTF-8. The deadline remains cooperative around bounded reads, lines, and regex calls; Python cannot force-interrupt a currently executing filesystem or regex operation without isolation, so this is not claimed as a hard wall-clock guarantee.
- Stable resume/model-switch identity behavior, centralized transcript sanitization, live history behavior, explicit partial glob/line/file/deadline results, and cancellation recovery remain covered by the focused regression suite.
- No packaging, signing, installation, or native Talk validation was run. This report contains no token values, credential contents, or token fragments.

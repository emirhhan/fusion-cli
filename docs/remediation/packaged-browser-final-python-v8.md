# Independent Python review: packaged browser cache

**APPROVE** scoped commit `05454ff096c630d42ae8b1f486c1c709e37a5beb`. No actionable CRITICAL, HIGH or MEDIUM findings remain in the reviewed change.

Reviewed files are `desktop_build/runtime/entrypoint.py`, `tests/test_runtime_entrypoint_environment.py`, and `docs/remediation/packaged-browser-cache-v8.md`. A complete archive of that commit was reviewed; concurrent automatic-teacher changes were excluded. Final owned-file hashes still match the shared worktree. The entrypoint SHA256 is `10a34331452e1975e4ad3f49b08f19bea6ed9f97e8d61d25a4fe0adaa0d49b36`.

The frozen entrypoint supplies an empty default for `PLAYWRIGHT_BROWSERS_PATH` before importing the CLI. Playwright's actual `PipeTransport.connect` otherwise inserts `0` for frozen execution, which selects its hermetic browser location. The empty value lets Playwright choose its normal platform cache without adding a platform-specific path or downloading a browser. Explicit caller values, including `0`, remain authoritative. The existing environment loader permits a nonempty user dotenv value to replace the bootstrap's empty default.

## Independent verification

- Scoped startup and runtime packaging tests: **33 passed, 4 skipped**. All four skips are existing Windows listen-adapter cases requiring native Windows `csc`; they were not run on this macOS review.
- **9 fresh independent checks passed**. These exercise the real installed Playwright transport method with a recording subprocess replacement. They reproduce frozen/unset becoming `0`, prove the bootstrap value exists before CLI attribute import and reaches transport construction, preserve explicit `0`/custom/empty values, exercise real dotenv loading for `0` and custom paths, retain a nonempty process override, and show importing the entrypoint alone changes neither the environment nor CLI execution.
- Ruff and format checks passed on the two modified Python files.
- Mypy passed for the entrypoint with `MYPYPATH=src`.
- No product/original/config edits, dependency installations, real browser/process launches, native UI operations, network services or model calls occurred. All review process handles are terminal.

The fix does not provision missing browser binaries or weaken unmeasured/error evidence. A caller explicitly selecting a missing custom or hermetic cache continues to receive the existing failure. Final acceptance must rebuild the runtime and confirm its actual packaged browser and native report verification. This scoped approval does not establish those later outcomes or overall product completion.

# Parent fixes E08/E09 and remaining E10

## Local typography

Chrome and PWA bundle the existing Inter variable font and its license locally.
Assistant prose is 16px/1.6; compact interface controls retain their existing
sizes. Both Tauri platform resource maps include the font/license. PWA serves
the font with `font/woff2`; its cache generation includes these local resources.
No CDN or additional host/font permission is introduced.

Actual ASGI font/license delivery failed with405 before the patch and passes
afterward, matching the original font bytes. Font rendering still needs live QA.

## Packaging metadata

Before removing any old output, build_runtime requires installed fusion-cli
metadata to match the source version. Direct .spec invocation also checks the
actual source __init__.py version. The actionable error explains an offline,
no-deps editable metadata refresh and the possibility of legacy egg-info shadowing.

Two regressions failed before implementation and pass now: stale0.7.18 and
missing distribution cannot reach PyInstaller or delete the old output/work
sentinels. Direct script invocation with only src on PYTHONPATH also passes.

Whole-code review exposed an imported-package/check-out mismatch: an old import
and equally old installed metadata could agree while differing from checkout
source. Both the early guard and manifest now read the checkout's literal source
version via AST without importing the installed package. Direct .spec invocation
uses the same reader. Two additional red/green cases preserve old output under
that mismatch and prevent the manifest from using a stale imported version.

## Credential blocking

WebProviderAdapter's entire credential-and-transport operation now runs under
its existing request timeout. Synchronous credential factories run outside the
event loop in a process-wide single daemon worker. A native call cannot be
forcibly killed: even after timeout/cancel it keeps the worker slot until it
actually returns. Subsequent callers wait asynchronously under their own deadline
without spawning more native workers. Daemon lifetime avoids default-executor
shutdown waiting; no credential value is globally cached here.

Cancellation propagates; late values are discarded; a closed event loop receives
no callback. Native error details are not copied into model/log error strings.
Three regressions were red on the old synchronous implementation and green now:
responsive/cancellable loop, bounded worker count after timeout and recovery,
and sanitized credential exceptions with slot recovery. Existing web registry
and adapter tests pass. Synthetic tests never touched a real Keychain or secret.

The native API may remain blocked in its sole daemon worker until the OS returns;
this patch guarantees responsive requests and bounded resource use, not the
ability to terminate macOS Security IPC or bypass its authentication.

## Verification

Parent-owned credential/registry/session, metadata guard, static asset, remote
service and PWA worker tests exited0. Ruff and scoped mypy passed before review.
All fixes require independent code/Python/JS review and packaged/live acceptance
before the final integration is reported complete.

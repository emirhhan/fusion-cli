# Frozen runtime browser-cache correction

The installed `da76120e` runtime could create a current HTML report but could not
measure it in a browser. Both layout and visual checks reported `Error` and
correctly retained unmeasured warnings. Those warnings were not model findings
about the document's layout.

## Cause and reproduction

An isolated MCP call to the actual installed frozen runtime started only a
headless blank browser session. It failed before opening any external page:
Playwright searched its bundled driver directory for
`.local-browsers/chromium_headless_shell-1243/.../chrome-headless-shell`.
That directory does not exist. The matching Chromium revision is already present
in the normal user browser cache.

Playwright's `PipeTransport.connect` sets `PLAYWRIGHT_BROWSERS_PATH=0` when
`sys.frozen` is true unless the variable already exists. Fusion's runtime recipe
intentionally collects Playwright but leaves browser binaries in the separately
installed user cache. The implicit hermetic directory therefore contradicts this
packaging policy.

The same frozen runtime with an explicitly empty `PLAYWRIGHT_BROWSERS_PATH`
successfully started a headless blank page, listed that page, and closed it.
No model, native UI, profile import, external URL or form operation was used.

## Narrow change

The runtime entrypoint now supplies that empty default before invoking the CLI,
only when frozen. Playwright then selects its normal platform cache. Explicit
process values, including `0`, custom paths and an empty value, remain unchanged.
The real environment loader also retains a later nonempty user `.env` override,
because it treats the bootstrap's empty value as unset.

No browser is downloaded or copied, no browser version is substituted, and no
measurement result is fabricated. A genuinely absent cache or explicit unavailable
override still fails through the existing honest unmeasured path.

## Evidence and limits

Evidence directory:
`work/reliability-v2/packaged-browser-fix-v8` in the parent task workspace.

- `frozen-browser-repro.json`: original frozen failure, headless blank only.
- `frozen-cache-control.json`: same binary with the empty-value control; page
  listed and closed successfully.
- `entrypoint-red.xml`: original entrypoint fails the frozen-startup regression;
  explicit-value and source-mode controls pass.
- `final-selected.xml`: runtime-entrypoint, metadata, health and pure bundle tests.

This is not a claim that the old installed runtime was patched. The parent must
review this source, rebuild the runtime and verify the actual installed browser
and visual checks on the report before treating native verification as complete.

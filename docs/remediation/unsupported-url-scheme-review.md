# Unsupported URL scheme normalization

Base snapshot: `17a07647`. Scope: browser/web input normalization and existing
unsupported-file error guidance. No application build or installation changed.

Both `browser.normalize_url` and `web._normalize_url` previously recognized only
lowercase HTTP(S) prefixes. Inputs such as `file:///tmp/report.html` became
`https://file:///tmp/report.html`, so the SSRF gate attempted to resolve host
`file` and reported a misleading DNS failure. Uppercase HTTP(S) was also prefixed.

A shared scheme detector preserves explicit URL protocols for the existing
HTTP(S)-only policy to reject before DNS, HTTP or browser startup. Bare domain,
IP, localhost and bracketed IPv6 port inputs retain existing defaults: browser
loopback URLs use HTTP, web-fetch bare URLs use HTTPS. Numeric bare host:port
syntax remains accepted; HTTP(S) and file schemes remain explicit even when their
payload is numeric. No file access or local-network permission was added.

The existing file rejection now explains recovery: serve local HTML with
`start_preview`, then open its returned HTTP address using `browser_open`.
Other unsupported protocols retain the concise existing HTTP(S)-only error.
Diagnostics identify the scheme without echoing an entire supplied URL.

Verification:

- Initial dedicated regression run: 25 failed, 12 passed before source edits.
- Separate preview-guidance regression failed before its guidance change.
- Final bounded eight-file browser/web/SSRF/error-classification suite: 107
  passed in 5.67 seconds, including 40 dedicated normalization/rejection tests.
- Ruff check/format passed for all changed Python files; mypy passed for the
  three source files.

Python/general independent reviews are pending integration by the parent agent.
This source snapshot requires a follow-up native build to reach the installed
application; the parent's frozen `17a07647` build remains separate.

## Scheme check before preview exception

Independent review (`71aebedc`) found that browser preview permission was applied
before scheme validation: an allowed `localhost:5173` authority also admitted
`file`, FTP, gopher, WS and custom protocols. Five product regressions reproduced
browser startup on those invalid URLs before the fix; four HTTP(S), including
uppercase, controls passed.

`browser_block_reason` now delegates unsupported schemes to the existing policy
before considering the loopback exception. Thus the preview permission grants
HTTP(S) only, and file errors retain the actionable preview guidance. No other
SSRF, DNS or local-origin policy changed.

Final validation: 127 tests passed in 6.22 seconds across the eight relevant
product files plus the independent review test file (all 11 external cases
passed). Ruff check/format and web-module mypy passed. Independent final review
and any application rebuild remain with the parent integration workflow.

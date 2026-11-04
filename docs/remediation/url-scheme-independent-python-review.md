# Independent Python review: URL scheme preservation

Reviewed source: `2b947b008c2e35d13301dcd7f28f19cf281c5209`.
Verdict: **BLOCK** pending the browser policy ordering correction below.
No production files changed by this reviewer.

## HIGH: allowed preview origins bypass the unsupported-scheme policy

File: `src/fusion_cli/tools/web.py:441` (`browser_block_reason`), newly exposed
through the normalization change in `src/fusion_cli/tools/browser.py:80`.

The local-origin exception returns success before checking whether the URL uses
HTTP(S). With `context.local_origins = {"localhost:5173"}`, each of
`file://localhost:5173/private`, `ftp://localhost:5173/private`,
`gopher://localhost:5173/private`, `ws://localhost:5173/private`, and
`custom+test://localhost:5173/private` now passes the actual `browser_open`
address gate and reaches `_sayfa` browser startup. The independent test replaces
startup with a recorder; it does not navigate or perform local file access.
This demonstrates a policy bypass, not a successful exploit of a browser's
protocol implementation. Previously the normalizer obscured these schemes;
preserving them correctly makes the existing ordering flaw reachable directly.

Fix: reject unsupported schemes before granting the allowed-loopback exception.
Use the same HTTP(S)-only rejection and file preview guidance as `url_block_reason`;
keep allowed HTTP/HTTPS preview origins functional without DNS. Add actual
entrypoint tests with a populated allowed-origin set, not only empty-context tests.

## Evidence

- Independent Ruff check passed for the three source files and new normalization
  test file; mypy passed for all three source files.
- Four-file baseline suite passed: 71 cases across URL normalization, browser local
  origins, pinned web egress and site-capture SSRF.
- Independent actual-entrypoint suite: five failures (unsupported protocols reached
  browser startup), six passes (four HTTP(S) case controls and two file guidance /
  credential redaction controls).
- Independent test and full failure log are stored outside the repository under
  the task workspace: `work/reliability-v2/test_review_url_scheme_gate.py` and
  `work/reliability-v2/python-url-independent-review.log`.
- Terminal session `72185` completed successfully; no reviewer test sessions remain.

Reviewed SHA-256 source fingerprints:

- `url_input.py`: `9e3f5ccf9effe7ae46c9b48cae7b2af9e1196d25f4c98f40b4f8f8b7fd54c706`
- `browser.py`: `fc656c96ffc1fdd9ca8ff227272f75099047dbe66e8596bc64aca87b819280f7`
- `web.py`: `7b6df4c52fe26f27b62830c0f782664be681d2caaa598c5b99dc9f9f2d3f6229`

Other instruction-loading work in the shared working tree was excluded. This
review does not approve integration or claim the installed app contains this change.

## Final re-review: HIGH resolved

Source `1ee40981b2498735282da7e9844b53ab627859d8`, inspected at combined
HEAD `790b396bae161899b661b13f756f02dc0a92294d`, rejects unsupported schemes
before the local-origin exception. All 11 independent entrypoint/control cases
now pass, including no DNS/browser startup for unsupported preview-origin URLs
and retained uppercase/lowercase HTTP(S) local preview permission.

**URL scope APPROVED.** No HIGH/CRITICAL findings remain in this URL change.
Shared static checks passed (Ruff; mypy nine source files), and the combined
instruction/URL regression run passed 171 cases. No reviewer terminal remains
running (session `11340` completed with exit 0). Final web source SHA-256:
`2c6eab938825bfcac8ef87f0e1757b1cbc15ae91e4f82dfbcf4e86159749b362`.
Other URL fingerprints above remain unchanged.

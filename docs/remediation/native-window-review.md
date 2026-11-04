# Native window and action-label review

Verdict: **APPROVE** for the reviewed standalone Swift delta since `a2137bba`. No open critical or high findings in this scope.

Reviewed source SHA-256: `0bddd0050e596feba344f1a0417602fa010c233d5fd54a7343ceff1133f5be61` (`src/fusion_cli/tools/data/desktop_host.swift`). Commit hash will be recorded after the implementation commit.

## Safety and identity

- Action labels are exported only for noneditable, known-safe `AXButton` branches supporting `AXPress`. Secure, input, unknown and editable branches remain excluded. Description and identifier must be strings, each limited to 256 characters; no arbitrary object descriptions or extra values are exposed.
- Selection hints require exact CG/AX window mapping. PID, explicit window-number conflict handling, and unique exact title/frame fallback remain strict. Partial scans that exhaust the metadata budget return unknown rather than a possibly ambiguous match.
- `is_main`, `is_focused`, role and bounded subrole are advisory. Unsupported data is omitted; no alternate window or action reference is executed automatically.
- Metadata uses an icon-free AX prepass, per-PID snapshots, a 350 ms overall budget, 10 ms AX messaging timeouts, and at most 16 candidates per complete snapshot. Unknown or exhausted metadata is omitted. Diagnostic candidate output is limited to eight windows plus the focused window, only for the requested PID; it includes roles, booleans and counts, not titles, values or contents.

## Review corrections

The initial draft ignored failure while setting the focused window's AX messaging timeout. The final source drops that focused element when the timeout cannot be set, so diagnostics do not query it with an unbounded default timeout. The unnecessary optional force unwrap in the deadline helper was also replaced with `guard let`.

## Verification

- `swiftc -typecheck src/fusion_cli/tools/data/desktop_host.swift`: passed.
- Synthetic tests for display/labels, strict window fallback and helper packaging: **18 passed in 2.69 seconds** across `test_desktop_display_value.py`, `test_desktop_background.py`, and `test_native_helper_packaging.py`.
- `swift build` and `swift test` cannot apply: this repository has no `Package.swift`; the helper is embedded standalone Swift. Both commands returned that explicit error. SwiftLint is not installed.
- Tests used the existing project Python environment. No live desktop helper, UI automation, private chat, or real application contents were accessed by this review.

This approval does not establish live Calculator acceptance. Selection metadata may be unavailable within the budget. The parent must independently verify the actual display reaches 0 and then 391; model text and synthetic fixtures are not proof of those effects.

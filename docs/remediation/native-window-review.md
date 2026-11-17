# Latest review: AX action diagnostics and native Calculator producer

Verdict: **APPROVE** for `481d4da5..9ab97f5f`, including diagnostic commit `c654f35f`. No open critical or high findings in this bounded Swift/native-output scope.

Reviewed final Swift SHA-256: `6e8ddfce671851903744ee0ee77bb856e8faaff9305ababd57fdd1798a3f61ef`.

- The action guard retains all four existing requirements: complete tree, exact fingerprint, unique identity, and matching path/identity. Rejection reports only boolean reasons and a histogram of eight fixed CF type categories over at most 500 entries. No AX values, object descriptions, token contents, or application text are added to diagnostics. The existing fingerprint algorithm is unchanged.
- The public failure adapter forwards only the four named boolean checks and the eight named integer counters in range 0–500. Wrong types and extra diagnostic fields are omitted.
- Successful dispatch still performs at most one AX press or set-value operation. Diagnostic generation does not retry an action or choose another reference.
- `system_calculator` is produced by the native `appInfo` path using `NSRunningApplication(processIdentifier:)` for the actual requested PID. Positive attestation requires the Apple Calculator bundle identifier and both resolved bundle and executable paths at their exact `/System/Applications/Calculator.app` locations. The producer exports only a boolean; it accepts no tool-argument attestation and exposes no URLs. A matching bundle identifier alone is insufficient. The pure helper tests reject wrong/missing IDs and URLs, non-file URLs, an executable outside the system bundle, and a symlink to an impostor bundle.

Verification on this exact native source: full `swiftc -typecheck` passed; **12 synthetic display/background tests passed in 3.70 seconds**. No live native helper, AX probe, application contents, UI, or private chat was accessed by this reviewer. The repository remains standalone Swift without `Package.swift`; SwiftPM build/test and SwiftLint limitations from the earlier review still apply.

This approval excludes the separate Python Calculator-consent consumer and any fingerprint canonicalization change. It does not establish that the live rejected AllClear action is fixed: the diagnostic build is intended to identify the unchanged guard's rejection reason. Parent runtime acceptance must verify actual application state independently.

---

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

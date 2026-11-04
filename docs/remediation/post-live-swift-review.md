# Post-live Swift review

Snapshot: `449813bfcfe509b821f7cdf7f218f37b54f875cd`, diff from `d8c5f6b5`. Scope: native static-text export and its privacy boundary only.

Initial decision: block pending the unknown-ancestor editability fix below. Both findings are resolved in `ec0acde79b7297c378b9444f3b05b2d845439671`; the bounded follow-up review approves that Swift source snapshot.

## Findings

1. **HIGH — Failed ancestor editability reads can authorize descendant export.** `src/fusion_cli/tools/data/desktop_host.swift:87–89` collapses every non-success result from `AXUIElementIsAttributeSettable` to `nil`. `displayBranchIsSafe` at lines 68–73 permits that unknown value for every role except `AXStaticText`. Consequently, an `AXGroup` or custom container whose AXValue is editable but whose query temporarily returns `.cannotComplete` passes `branchSafe = true`; a noneditable static-text descendant can then be exported. This contradicts the stated unknown-classification fail-closed boundary. Preserve the status: distinguish explicitly unsupported/absent value capability from failed queries, and propagate an unsafe branch for other errors. Keep noneditable static-text eligibility dependent on a successful settable query. Add fixtures covering failed ancestor queries separately from explicitly unsupported window/container attributes.

2. **MEDIUM — Export accepts descriptions of arbitrary AXValue types.** At `src/fusion_cli/tools/data/desktop_host.swift:90`, `String(describing:)` converts every returned CF value into an exportable string. An `AXStaticText` with a non-string AXValue therefore emits an implementation description as authoritative `value_source: AXValue`, rather than rejecting the unexpected type. Preserve the existing description for fingerprint compatibility if needed, but independently require a string AXValue for display export; test non-string values produce no display field.

## Verified properties and limits

Follow-up review of `449813bf..ec0acde7`: `displayEditability` preserves successful read-only/editable states, explicitly unsupported/absent capability, and unknown failures. Unknown failures reject every branch and propagate to descendants. Static-text export requires a successful read-only classification. The export gate accepts only a string cast from the raw AXValue; the description remains solely in the existing fingerprint path. The added fixtures cover actual AXError classifications, descendant denial, supported string bridging, and rejection of non-string values. No remaining actionable findings in this bounded follow-up.

Independent follow-up validation: `swiftc -typecheck src/fusion_cli/tools/data/desktop_host.swift` passed. The focused test command `uv run pytest -q tests/test_desktop_display_value.py` could not run because `pytest` was unavailable. That command created a local environment and installed the project/dependencies before failing; no native helper or UI ran. The parent's seven passing focused tests remain parent-reported evidence, not independently reproduced here.

Role/subrole unsuccessful reads and failed string casts return unknown; unknown or empty roles, secure/password metadata, explicit input roles, editable elements, and already unsafe ancestors deny export. The 1000-character cap and truncation marker agree. Entry paths, identity construction, value-digest construction, and action/window identity checks remain unchanged by this diff.

`swiftc -typecheck src/fusion_cli/tools/data/desktop_host.swift` passed independently. No native helper/UI execution was performed. The standalone script has no SwiftPM manifest; application builds and runtime execution were outside this review. SwiftLint is unavailable. Parent-reported scripted fixture results were not independently rerun. Review assumes required CI is green and merge conflicts are resolved.

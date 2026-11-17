# Native target identity review

Decision: approve the bounded Swift patch. No actionable CRITICAL, HIGH, or MEDIUM findings.

Reviewed `496316da..f1043eae`, restricted to the 19 added lines in `src/fusion_cli/tools/data/desktop_host.swift` (129–139, 154–156, 165–167), with existing `targetWindow`/`windowFrame` and the Python identity consumers read for context.

- The CG row must belong to the observed PID. An explicit AX window number must match the CG ID; a conflicting explicit number cannot use geometry fallback.
- Without an explicit number, matching requires exact AX/CG title and frame equality. Enumerating all onscreen rows and requiring exactly one match rejects duplicate candidates. Missing AX windows, missing frames, and zero/multiple matching rows omit the window identity; the interactive Python guard rejects that omission.
- The payload uses the AX frame in global screen coordinates, without pixel scaling, AppKit coordinate flipping, display clamping, or main-screen offset assumptions. This is consistent with the existing AX point lookup and identity comparisons, including negative secondary-display origins. Retina pixel dimensions are not introduced by this patch.
- Point probes derive the window from the hit AX element; foreground probes derive it from the foreground application's focused window. PID-only probes remain unchanged.

Validation: `swiftc -typecheck src/fusion_cli/tools/data/desktop_host.swift` passed on this worktree. SwiftLint is unavailable. This standalone helper has no Swift package manifest, so SwiftPM build/test are not applicable; application builds were excluded by the review task. The parent's reported 392 scripted tests were not rerun in this bounded review. No helper execution, native UI interaction, or live multi-display/Retina validation was performed. Approval assumes green required CI and resolved merge conflicts; type checking does not establish native runtime behavior or eliminate focus changes between observation and event posting.

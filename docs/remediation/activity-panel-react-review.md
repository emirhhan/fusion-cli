# Activity panel React review

## Viewport containment closeout

**APPROVE at `59a755d4`**, reviewing its ten-file geometry delta and the React handoffs to the previously approved panel. No remaining actionable CRITICAL, HIGH or MEDIUM React finding was identified in this bounded scope. Concurrent visible-history/backend work is excluded.

The portal stays inside its owning conversation frame. Its noninteractive, frame-sized clipping host prevents stale wide geometry from extending the document during narrow resizing; only the bounded pane receives pointer events. Coordinates use the actual conversation viewport, preserving the Composer area and the measured two-row flow placeholder. Focus/blur ownership includes the portalled pane, while the connected external-focus and explicit-user-request rules remain intact. Placement observers and scroll/resize/visualViewport listeners have matching cleanup and are active only for an open pane or expanded preview. No dispatch, permission, modal/inert or execution policy was changed.

Independent final checks:
- **2 geometry browser cases passed**, Chromium and WebKit, 5.0 seconds. Both placed the 470px pane at 314.8125–784.8125 inside a conversation ending at 792.8125, while preserving outer scrollTop. Last-row/code scrolling, 430×650 resizing and session cleanup passed.
- **6 focus browser cases passed**, both engines, 5.1 seconds: external Composer protection, focused-row migration, and explicit opening/closing.
- **40 targeted React tests passed**, five suites, 4.39 seconds.
- Canonical hooks lint, strict exhaustive-deps checks on the panel/placement hook, application TypeScript and exact-commit whitespace checks passed. The three production geometry files still byte-match `59a755d4`.

Real installed-native acceptance, the parent's full App suite and final packaging remain separate gates. Production source was not edited.

## Earlier panel closeout

**APPROVE at `897cf4fc`**, covering the React changes from `e7a82910` through `5030a75c`, `1cb2cca2` and the final WebKit correction. No remaining actionable CRITICAL, HIGH or MEDIUM finding was identified in this bounded review. Generic TypeScript, native shutdown and packaging have separate owners.

## Closed findings

- Streaming 2→3 activities previously moved focus from the Composer to a summary. The first fix depended on `relatedTarget`, which real WebKit can report as null during an external focus change. An independent WebKit reproduction at `1cb2cca2` explicitly observed TEXTAREA with the draft before the update and SUMMARY afterward. Final code checks the currently connected external active element and permits a one-shot override only for explicit user opening/closing. The body/html reparenting gap still permits restoring the previously focused row.
- Normal view previously discarded earlier model-block reasoning despite the explicit showSteps preference. Final code collects non-tool steps into one disclosure per turn and retains tool-associated thinking in its own row, only when the preference is enabled.
- Suppressed events no longer produce empty grid wrappers. The two activity previews and single status remain bounded while reasoning and final answers remain accessible.

## Independent final verification

- Canonical WebKit focus project: **3 tests passed**, 16.2 seconds. This covers the actual Composer draft/focus during background append, focused-row reparenting and explicit mouse/keyboard opening/closing with meaningful focus return.
- Five targeted React suites: **40 tests passed**, 9.83 seconds (activity panel, ActivityLine, legacy ActivityLine behavior, work grouping and stick-to-bottom).
- Canonical hooks lint, strict exhaustive-deps checks on the new panel and modified scrolling hook, application TypeScript check and combined-range whitespace check passed.

Native UI acceptance, the parent's full App suite, final packaging and exact native viewport geometry are outside this verdict. No production source was edited. Temporary independent regression files were removed after each check.

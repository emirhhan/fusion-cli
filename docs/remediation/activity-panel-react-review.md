# Activity panel React review

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

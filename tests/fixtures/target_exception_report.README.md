# Target-size regression fixture

`target_exception_report.html` is the exact generated report captured in the configured-default-f9b acceptance run on 2026-11-05 (SHA-256: `3430945aaf2482b7dd3996789a593ddb8512223d0006f4c66a4b59d988e443dc`). Its factual content is unverified test data; this fixture tests DOM geometry only. Tests render isolated markup, block all network requests, and never follow its citation.

The sole citation is an inline prose link measuring approximately 222×17 CSS pixels in the original environment. The original dimensions-only probe incorrectly warned about WCAG 2.5.8. Regression tests independently retain crowded controls and cover isolated, spaced, exact-24px-circle-boundary, custom-role, hidden/nonvisual prose, focus-only containers, and truncated-candidate cases at mobile/tablet/desktop widths.

The probe applies only provable inline and spacing exceptions. It is bounded to 1500 candidates; if truncated, spacing cannot be proven and is not exempted. Inline proof scans at most 2000 original text nodes and requires rendered ranges and conservative visibility/flow checks; clipped or unprovable prose does not grant the exception. Bare tabindex is a keyboard-focus marker rather than evidence of a pointer action. Undiscovered JS event listeners, nonrectangular hit areas, equivalent controls, user-agent and essential exceptions remain unassessed. Remaining findings are potential issues, not definitive violations or full conformance results.

Missing-main is a separate semantic-navigation advisory; native `<main>` and a single `role="main"` token are recognized from parsed attributes rather than comments. Obvious nonrendered, template, explicit hidden/inert/aria-hidden, inline display:none/visibility:hidden, and overridden native-main roles are excluded. This is a static recommendation heuristic; external CSS, malformed HTML tree repair, and full ARIA role fallback are unassessed.

Primary references:
- [WCAG 2.5.8 target-size minimum exceptions](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- [WAI-ARIA main landmark examples](https://www.w3.org/WAI/ARIA/apg/patterns/landmarks/examples/main.html)

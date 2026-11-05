# Independent JavaScript review: browser target exceptions

Reviewed product commit `a19d61f35827a661d2be31009ce3c395912c7928`.
Verdict: **HOLD — follow-up required**.

The review scope is the browser JavaScript embedded in `browser_verify.py`,
particularly `_LAYOUT_PROBE`. This is a local frozen-commit review; PR merge
metadata is not applicable. No TypeScript configuration or ESLint target covers
this embedded string, so validation used Node 22 syntax checking and actual
Chromium DOM execution, rather than an unrelated application type check.

## Findings

1. **Hidden prose falsely proves the inline exception** (`browser_verify.py:795`).
   `cloneNode(true).textContent` includes text that is not rendered. A paragraph
   containing a hidden `Source:` span and two adjacent small links returns no
   small targets. Removing that hidden span correctly returns two candidates.
   The same failure occurs with `display:none`, `visibility:hidden`, `opacity:0`
   and a clipped, absolutely positioned screen-reader-only span. The exception
   must be supported by visible non-target prose, not merely DOM text. This
   regresses the explicit requirement to retain crowded-control detection.

2. **A bare focusable ancestor creates a false spacing warning**
   (`browser_verify.py:778`, `browser_verify.py:799`). An isolated authored
   16-pixel button passes alone, but placing it inside a padded plain
   `div tabindex="-1"` causes a warning because the ancestor's bounding box is
   treated as another activation target. Focusability alone does not establish a
   separate pointer control. Retain genuine role/handler controls while avoiding
   this false neighbor proof.

The W3C criterion permits the inline and spacing exceptions. The findings above
concern incorrect evidence for those exceptions, not a claim of full WCAG
compliance. A paragraph's prose appearing on another wrapped line is not by
itself a demonstrated violation: the criterion also permits targets constrained
by non-target text line height.

## Independent verification

- Extracted the frozen probe and ran Node 22 `--check`: passed.
- Ran `test_browser_target_exceptions.py` and `test_browser_verify.py` with the
  original Python environment and `PYTHONPATH=src`: **62 passed**.
- Executed eleven additional actual-DOM cases, then three hidden-prose variants.
  All browser requests were blocked; **zero network attempts** were observed.
- Confirmed visible inline prose, isolated buttons, spaced controls and crowded
  native buttons as positive controls. The expected original report case passes.
- No product source, preferences, profiles, native apps or model calls changed.

Evidence is under the task workspace at
`work/reliability-v2/browser-target-ts-review-v6/`: `probe.js`, `targeted.xml`,
`adversarial-results.json`, and `hidden-prose-results.json`.

Both findings were sent to the owning implementation worker. Approval is pending
its frozen follow-up and an independent rerun.

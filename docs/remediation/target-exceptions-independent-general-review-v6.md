# Independent general review: target exceptions and landmark advice

Reviewed `a19d61f3`, `54e1661f` and `12069aa1` in the separate pinned
`snapshot-12069aa1` source/test tree. Product files and selected regression tests
were byte-compared with `git show 12069aa1:<path>` before execution. Concurrent
worktree presentation/session edits were not imported or reviewed here.
Verdict: **APPROVE**; no actionable findings remain in this change.

The actual report citation no longer receives a dimensions-only target warning.
The probe excludes targets only when its inline-prose or spacing evidence supports
an exception. Crowded native/custom controls remain candidates; the resulting
warning explicitly states that it alone does not establish noncompliance. Bare
focusability is not confused with a separate pointer control. Geometry analysis
is capped at 1,500 targets; truncated sets cannot prove spacing. Inline-prose
search is capped at 2,000 text nodes and examines rendered, visible original DOM.

Missing-main advice is typed as an advisory. The parser recognizes a plain native
main or unambiguous main role while excluding the tested hidden, template,
nonrendered and overridden-role contexts. Unknown closing tags use dictionary
lookup; matched closers remove each ancestor at most once and clean per-tag
positions with popped descendants. This preserves exclusion context without the
previous quadratic ancestor search.

Neither the target heuristic nor the landmark hint claims a complete CSS/ARIA
accessibility tree or WCAG assessment. Existing form truth and network request
guards remain separate and were not weakened by the exception logic.

## Independent verification

- **Six additional overall-contract controls passed in 1.68s.** The exact report
  fixture was rendered at 375/768/1440 pixels with requests blocked and no network
  attempts. Its citation produced no small-target candidate. Crowded native/custom
  controls still produced a qualified warning. Landmark role/hidden/template
  controls remained nonblocking; actual WebVerifier retained a real form blocker
  alongside the optional landmark advisory.
- **128 existing tests passed in 71.84s** across target exceptions, parser
  complexity, verification severity, browser request guards and contact-form
  probes. No failures or skips.
- Ruff passed on both product files and two new test modules; scoped mypy passed
  on both product files.

Evidence: task workspace `work/reliability-v2/a11y-general-review-v6/`, including
independent controls, logs and XML. All test handles are terminal. No actual
provider, network, native app, user browser profile, package or installation was
used; only isolated headless Chromium test contexts were launched.

Reviewed SHA-256:

- `browser_verify.py`: `2a095d6b39977e6e732aac42bdf82c95a8f705a8465b445e9a8e7a8c2c31e024`
- `web_verify.py`: `106bd43f76cd3aa780cd5d08fa89e591381fda915e20ead1c8772784ee838514`

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **APPROVE**.

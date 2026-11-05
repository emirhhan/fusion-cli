# Live self-review result disclosure

`SelfReviewFinished` is now a persistent activity row in the existing work panel.
Only explicit `completed: true` together with a boolean `issue_found` identifies a
completed assessment. An incomplete review says “özdenetim tamamlanamadı”; missing
or malformed completion/finding fields remain unknown. Neither missing findings
nor `issue_found: false` by itself establishes that review completed.

Completed rows describe the review and whether it reported a finding. They never
declare that all requirements passed. Incomplete/unknown rows do not set a turn
outcome or turn the job into a generic failure. Event reasoning and arbitrary
payload text are not displayed.

The document-only proof card label is now “Dosya denetlendi”. Other delivery-card
labels are unchanged. This scopes the label to observed file verification and
avoids implying that every fact or optional model review completed.

This follow-up changes live event presentation and scoped copy only. It adds no
backend wire fields or history persistence contract. The existing public history
event whitelist does not replay self-review events; the live-only limitation is
intentional in this change and must not be represented as persisted review proof.

Validation includes failing-first event/card/activity controls, normal and issue
completion, incomplete review, malformed/absent fields, unchanged non-document
labels, absence of reasoning text, and preservation of the existing two-row work
panel. The separate frontend evidence-detail implementation retains its own
bounded decoder/history contract.

Eight missing-behavior failures were observed before this follow-up. Final checks:
109 focused tests and 2,430 tests across 303 application files passed; no failures
or pending tests. TypeScript, hooks lint, production build and whitespace checks
passed. The Chromium/WebKit keyboard, scrolling, file-link and 13px/400 fixture
also passed after the label change, with zero network requests. Full JSON reports
and the failing-first report are retained in the task workspace under
`work/reliability-v2/document-delivery-frontend-v6/self-review-*.json`.

# Independent review: research tool preference

Reviewed commit `449831ac533ac9e9b076a5e7d660ef9aad5c6a46`.
Verdict: **APPROVE**; no actionable findings.

The root prompt now prefers existing web search/page reading for current facts
instead of unnecessarily generating command code. The preference preserves an
explicit user command request and other authorized paths when web tools are absent
or fail. It adds no shell prohibition, permissions, provider call, routing change,
or procedural tool-name instruction. Source/date/factual evidence requirements
remain unchanged. The two shortened verification statements retain relevant
test/lint/build/runtime checks and verification of actual requested behavior.

Independently executed **82 tests across eight modules**, all passing in 9.82s:
system prompt diet/layers, prompt contracts/manifest, identity contract,
consistency, scoped source reads and teacher plans. The prompt remains 6,096
characters under the existing 6,100 limit. Reviewed SHA-256:
`71299a1a7d92b4f9dce6db85be73b422a4fe752947d5f56504e1b044e77220a9`.
Logs/XML are in task workspace `work/reliability-v2/research-guidance-review-v5/`.

The worker's implementation note accurately limits its claims: these static and
scripted checks do not prove what tool the real model will select or that a live
research/artifact task completes. No real model, network, browser, native app,
package, installation or product-source edit was performed by this review.

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **APPROVE**.

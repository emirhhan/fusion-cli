# Fusion long task acceptance — 24 September 2026

## Gate

**Not accepted for a new release.** The clean GATE HOLDING worktree was isolated from the user's uncommitted project and contained no `.env` or stock-service credential file. All changes described below were made only in that worktree. No live WooCommerce request was made.

The task was to repair a real, missing stock-import UI integration across client modules, a server route, and tests; run TypeScript, Vitest, and build; and report limitations accurately. The initial clean checkout already failed `tsc` because `ImportPanel.tsx` imported missing `stokApi` and `types`. Its full Vitest baseline also had database/environment failures.

| Provider | Observed result |
| --- | --- |
| NVIDIA Nemotron 3 Ultra | HTTP 429 before doing project work. |
| NVIDIA Nemotron 3 Super | With the search fix, 42 model calls and 34 tool calls in 159 seconds; zero file mutations. It repeated searches and stopped for no progress. |
| NVIDIA DeepSeek V4.1 Flash | Desktop task was stopped after roughly seven minutes waiting on a model call, without project changes. |
| Gemini web | Wrote client modules, a Next route, and five client tests. `tsc`, focused tests, and Next build passed. The full suite still had baseline environment failures. Its success/security claims did not match independent checks. |
| ChatGPT web | Tool-capability probe failed: only half of four requested tool calls were selected in one run. A second run claimed a shell command and search had been executed without producing tool calls. Mutation access remains disabled. |

## Independent acceptance after the Gemini implementation

A reviewer follow-up added a production-mode POST restriction, an absolute shop URL, and two route tests. The process was stopped after more than 20 minutes when its correction phase returned to repeated configuration and URL searches. The independent acceptance tests were run against the resulting files:

1. A cross-origin POST to `/api/stok/run` in development returned **200**, and the route called the local stock service. Expected: reject before the service call.
2. `productUrl(1234)` resolved to `https://motogate.com.tr/wp-admin/post.php?...`, an administration editor URL. The UI label is “Sitede aç”; expected: a public product page.

Both tests failed. The tests are in the isolated worktree at `app/api/stok/__tests__/security.acceptance.test.ts`; they are not changes to the user's original GATE HOLDING checkout.

## Fusion fixes shipped to the working branch

Commit `1a22755` fixes project search stopping on large generated files, the API agent context gauge being narrowed by an unrelated enabled web session, NVIDIA Nemotron 3 tool-call request formatting, and reporting when a model claims success despite failed verification. It also gives the reviewer explicit checks for privileged proxy routes and cross-site links. The source and focused tests passed Ruff and mypy.

A further fix limits web-provider self-review to the configured judge timeout; this arose because the Gemini review continued for minutes despite a 12-second judge timeout. Its focused timeout test passes. The full Fusion suite reached 100% with one prompt-length budget failure; the prompt was shortened and the prompt-budget test then passed. The full suite was not rerun after that focused correction.

## Release decision

The acceptance gate requires a completed multi-file task, focused and build verification, a correct public link, a rejected unauthorized stock mutation, and an honest final status. It has not passed. Do not install or publish a replacement release based on this run.

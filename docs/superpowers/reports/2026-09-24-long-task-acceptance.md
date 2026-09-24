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

## Mixed-provider long-task replay

A second, fresh isolated GATE HOLDING worktree used Gemini web as the coding agent and ChatGPT web as the independent reviewer. The task ran for 527 seconds, with eight agent-model calls, 16 tool calls and six mutations. Its focused mock-fetch tests and TypeScript check passed. The reviewer emitted `issue_found=False`, and Fusion returned `ok=true`. Independent acceptance then failed **3/3** checks (`components/stok/__tests__/integration.acceptance.test.ts` in that worktree):

1. The new client calls `/api/stok/*`, but there is no matching Next route or rewrite. Those requests would return 404.
2. `ImportPanel` uses supplier codes `em` and `moy`, but the generated label table contains neither; the UI would show missing labels.
3. The “Sitede aç” link is relative `/urun/1234` on the GATE HOLDING app, not a public MotoGate store URL.

The agent's own four tests assert its invented URL and mock fetch responses. They do not exercise the server path. The reviewer likely timed out: the old implementation returned an empty string on timeout, then published the same `issue_found=False` event as an explicit clean verdict. A timeout is now reported separately as incomplete, and `npx vitest run` is now recognized as a behavioral command. A new Next route verifier is included in the automatic quality gate. Running it against the real isolated output produces a blocking finding for the missing `/api/stok/*` endpoint. This prevents that specific broken artifact from being reported as a clean successful turn.

When no post-mutation behavioral test runs, the report also now labels the agent's accompanying completion claim as unverified. The outcome flag still follows the existing policy that missing evidence alone is a warning rather than a failed turn; the release acceptance gate remains stricter.

## Fusion fixes shipped to the working branch

Commit `1a22755` fixes project search stopping on large generated files, the API agent context gauge being narrowed by an unrelated enabled web session, NVIDIA Nemotron 3 tool-call request formatting, and reporting when a model claims success despite failed verification. It also gives the reviewer explicit checks for privileged proxy routes and cross-site links. The source and focused tests passed Ruff and mypy.

A further fix limits web-provider self-review to the configured judge timeout; this arose because the Gemini review continued for minutes despite a 12-second judge timeout. Its focused timeout test passes. The full Fusion suite reached 100% with one prompt-length budget failure; the prompt was shortened and the prompt-budget test then passed. The full suite was not rerun after that focused correction.

## Release decision

The acceptance gate requires a completed multi-file task, focused and build verification, a correct public link, a rejected unauthorized stock mutation, and an honest final status. It has not passed. Do not install or publish a replacement release based on this run.

## Direct UI comparison

The source preview and a signed-in ChatGPT conversation were inspected at the same 1280×720 viewport in dark mode. The Fusion conversation composer was initially a tall two-row layout. Commit `69a0d8e` made short messages use a 640×54 single-row layout in both empty and active chats, with the dictation, voice, approval, attachment and model controls still present. A multiline task expanded to 119 pixels. The disclaimer moved to the conversation stream so the composer sits at the bottom like the ChatGPT reference. The installed Fusion app is older than this source preview, so its screen is not evidence that the new source is installed. The account menu was also checked interactively: before the fix it showed “Çıkış yap” while signed out and eight main entries extending far up the sidebar. The menu now shows “Giriş yap” while signed out and keeps Control Panel, Skills, MCP and Language under an expandable “Daha fazla” entry; those routes remained reachable in the live source preview. This is a targeted improvement, not full visual or functional parity.

## Fresh long-task rerun

A third clean detached GATE HOLDING worktree at `fusion-eval-gate-rerun` was created from `66b05da`. It contained no copied `.env` or live service credential. Gemini web was the coding agent and ChatGPT web the reviewer, using the same task and approval policy as the mixed-provider replay. The run completed in 1,243 seconds with 24 model calls, 36 tool calls, 17 mutating calls and two context compressions. Fusion returned `ok=false` and `partial`: the production build failed, and the last changes had no subsequent verification command. The reviewer timed out in final self-review (`completed=False`); that state was reported distinctly from a clean review.

The generated files still fail independent acceptance (`components/stok/__tests__/fusion.acceptance.test.ts` in the isolated worktree, 3/3 failed):

1. `productUrl(1234)` opens `/wp-admin/post.php` rather than a public product page.
2. An unknown POST action receives HTTP 200 and `success: true`.
3. An unauthenticated stock mutation receives HTTP 200 rather than 401/403.

The created GET route returns a fixed empty collection and zero counters. The created POST route returns success without calling a stock service. The agent also changed two unrelated `app/api/baffer` files while trying to clear TypeScript baseline errors; the build still failed. These changes remain only in the isolated worktree.

The Fusion branch now checks direct template-string API paths as well as constant-based paths, and flags a Next POST route that returns unconditional success without a service call. The latter rule detects this rerun's generated route when applied directly. The agent and review prompts also explicitly reject placeholder integration routes. A web-provider timeout regression test exposed that `CompletionRequest.timeout_s` was ignored; the adapter now applies it and returns a distinct timeout result. These guardrails need another long replay before release acceptance can change.

The desktop command bridge lists `/btw` as supported and returns the side question as a task; a focused protocol test passes. The agent loop also exposes `spawn_agent`, with three focused subagent tests passing. These checks establish that the entry points exist. They do not establish that an aside is isolated from the main conversation or that delegated long tasks meet the acceptance gate.

The desktop conversation no longer inserts a synthetic “running” assistant message before a macro task, including `/btw`. A UI regression test reproduces the previous duplicate message and verifies that only the user's command remains until the real turn answers. The aside still uses the ordinary turn and history; it does not run independently while another turn is active.

A fourth isolated replay ran in `fusion-eval-gate-fourth` for 1,529 seconds, with 15 model calls, 23 tool calls and 11 mutations. The final Next build failed with `ENOSPC` after the machine ran out of free space; the turn ended `partial`, and the last route edit was not verified. The independent reviewer failed and the final self-review timed out (`completed=False`). That infrastructure failure alone prevents accepting the run. Older isolated evaluation worktrees' reinstallable `node_modules` and `.next` outputs, plus a stale Rust incremental and bundled-runtime build cache, were cleared to recover disk space; their source and evidence remain intact.

Independent request-level checks against the fourth run's generated files failed **3/3** (`components/stok/__tests__/fusion.acceptance.test.ts` in the isolated worktree): the “Sitede aç” link opens `/wp-admin/post.php`, an unauthenticated POST returns 200, and a cross-origin POST also returns 200. The latter two tests mock the local stock service and prove the route calls it before checking the requester; no live stock service or credentials were used.

After recovering disk space and generating the local Prisma client (the isolated dependency install had skipped package scripts), `npx tsc --noEmit` and the Next production build both passed on the fourth worktree. The original in-run build failure was environmental. The 3/3 request-level failures remain, demonstrating that TypeScript and Next build success do not establish safe or correct behavior.

The fourth route forwards POST through the existing local stock client, which injects the privileged `X-MG-Panel` header, but does not check the calling user's authorization. A new deterministic route check flags that exact generated artifact. The check looks for a local loopback helper with that privileged header and a POST route without an explicit caller authorization call. It is a blocking heuristic, not proof that an authorization call is effective; independent request-level tests remain required. Release acceptance remains failed even if the infrastructure-only build failure is disregarded.

Fusion verification after the changes: the full Python suite passed after freeing disk space; the focused Next-route tests, Ruff and mypy passed; the React suite passed 709 tests across 93 files, and its production build passed. The isolated fourth worktree passed TypeScript and Next build after Prisma generation but failed all three independent behavioral checks. These results support keeping the Fusion branch as development work, without replacing the installed app or publishing a release.

## NIM catalogue and web teacher follow-up — 25 September

The installed configuration had verified Gemini and ChatGPT web sessions but `teacher=None`, so the agent registry never exposed `ask_teacher`. Fusion now selects a verified enabled web session as its teacher when no explicit `teacher:` is configured, and refreshes that choice when a web account is verified, disconnected, or its selected model changes. The Models settings view shows the selected teacher. A real `ask_teacher` call through the local registered Gemini 3.1 Pro web session returned an answer about testing the client-to-route contract. This proves the connection and tool path, not that every agent will choose to use it or that its advice is sufficient.

The live NVIDIA catalogue returned 82 IDs for this account. The old composer list exposed only four of them because it filtered against a fixed tier list. Fusion now exposes the catalogue entries and probes an NIM selection with a real structured function call before applying it; a listed ID alone is not treated as usable. Several listed models returned 404 or timed out in direct probes. GLM 5.3, GLM 5.3 Flash, Nemotron 3.5 Lightning, Mistral Nemotron, and Nemotron 3 Ultra produced a valid simple tool call in this session. NVIDIA documents the broad catalogue as spanning multiple model use cases, and its LLM API uses `/v1/chat/completions`; this supports checking chat/tool capability per model rather than assuming it from catalogue presence ([NVIDIA catalogue overview](https://docs.api.nvidia.com/nim/docs/introduction), [NVIDIA LLM API](https://docs.api.nvidia.com/nim/re/reference/llm-apis)).

The simple probe did **not** predict advanced task success. A strict single-model GLM 5.3 Flash run on the same isolated GATE import task was stopped after about 16 minutes and had made no file changes. It spent model calls reading and searching; one read of a large tool-output artifact failed because the artifact lived under the session memory directory outside the restricted project root. The artifact path is now readable only when the same session's ArtifactStore created that exact file; write tools and unrelated outside-root files remain restricted. Artifact reads are split into bounded chunks to avoid re-offloading themselves. Focused artifact access tests pass.

A second strict single-model run with Mistral Nemotron finished after 261.7 seconds, two model calls, zero tool calls, and zero mutations. Its first model response took about four minutes. Mistral Nemotron was therefore removed from the curated automatic coding pool; it remains visible as a catalogue model subject to the live selection probe. The agent stream now has an absolute per-call timeout so token trickles cannot keep the visible “thinking” state alive indefinitely. A never-ending streaming-provider regression test confirms that cancellation and a failed outcome occur at the configured limit.

The first automatic-teacher run with Nemotron 3 Super ended after 66.5 seconds, seven model calls and five read/search tools without editing. It stopped before the original ten-tool threshold, so no consultation occurred. The threshold was changed to five non-mutating tools for complex mutation tasks. Fusion now performs one bounded `ask_teacher` call at that plateau, placing the answer in a normal tool-result message for the next model turn. The task excerpt sent to the selected web session is limited to 700 characters and passed through the central secret/PII masker; an email-only redaction fast-path bug was corrected. A fake-provider end-to-end test verifies one consultation and the masked email.

In the second real Nemotron 3 Super run, the consultation happened after five read/search tools and Gemini web answered successfully in 43 seconds. Nemotron continued reading but never edited; the run ended after 204.2 seconds, 20 model calls, 18 tools including `ask_teacher`, and zero mutations. The teacher's answer named `types.ts` as a first change but also proposed type names without code evidence and said its own environment had no write tools. This is evidence that the teacher path works, and equally clear evidence that the apprentice still did not complete the task or make good use of the advice. Automatic consultation is now confined to the top-level task to avoid duplicate web calls from nested agents.

A strict GLM 5.3 run on the same isolated project also consulted Gemini web and spent more than eight minutes reading source, tests, documentation and Git history. It produced zero tracked file changes. Its attempt to run a shell command that would read `services/stok/config.json` was denied by the isolated evaluator's safety policy. The independent web reviewer did not return promptly, so the evaluator process was terminated; this is an interrupted run, not a completed acceptance. The isolated checkout still has no tracked changes. The run supplies no evidence for release readiness.

An English mutation-intent gap was also corrected: the GATE task's “Implement a coherent ... flow” had been classified as no required change, so the mutation-evidence policy did not apply. The new narrow English patterns classify that task as a workspace mutation while preserving explanation-only questions. The long-read plateau hint can now activate for this task, but its real-task effectiveness has not passed acceptance.

Quality checks for this follow-up: the full Python suite passed twice (four existing skips); focused agent/teacher tests after the final one-consult guard, Ruff and mypy passed. The Models settings tests passed (17), and the React production build passed. These source checks do not overturn the failed long-task acceptance gate. No new app installation or GitHub release is warranted yet.

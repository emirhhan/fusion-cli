# Activity panel general code review

Final snapshot: `5030a75c`, `1cb2cca2` and exact final WebKit correction `897cf4fc`, restricted to these UI changes and immediate rendering/protocol/session consumers. Verdict: **APPROVE — all tracked P2 findings closed, zero open findings.**

Final macOS/WebKit closeout: reviewed the exact four-file `897cf4fc` diff. A connected active element outside the panel now blocks focus transfer during automatic stream-driven opening, independently of a stale/null relatedTarget. Body/html transient focus gaps still allow the selected row to recover focus during reparenting. A one-shot explicit user-intent ref permits deliberate open/close to move focus meaningfully from an outside draft, then is cleared when consumed. No message, draft, session, permission or backend payload is changed by this guard. The dedicated focus configuration runs only the three relevant contracts on Chromium and WebKit, retaining the shared fixture/server settings.

Independent final validation: all 13 activity-panel unit tests passed under Node 22; combined UI range whitespace checks passed. Read the independent React review's final WebKit reproduction/closeout: the first correction still moved TEXTAREA to SUMMARY in WebKit, while the final three WebKit focus cases passed at `897cf4fc`. That browser run was not duplicated by this general reviewer. Earlier geometry/reasoning fixes remain intact. Parent full-App testing was still separately owned and is not claimed complete here. No production edits, private/actual user UI, network, `uv`, native build, Cargo or broad suite rerun was performed.

Corrective closeout: all three previously tracked P2 findings are resolved. Focus transitions are now conditional on panel focus ownership; a real outside focus target relinquishes that ownership, while a null relatedTarget during internal row reparenting retains it. The new browser fixtures cover both a focused summary moving into the pane and a genuine Composer retaining focus and editable draft during a 2→3 append. Conversation filters null messages before creating grid wrappers, while preserving the first actual panel and result/change/narrative nodes. Explicit showSteps collects earlier non-tool reasoning into one collapsed StepList, without reintroducing duplicate status/tool trails; panel tool thinking is also gated by that preference. With showSteps off, that additional thinking content is absent.

Independent correction validation: 25 focused activity-panel, ActivityLine and scroll-hook tests passed across three files under Node 22; combined commit whitespace checks passed. Reviewed the exact six-file correction and its browser regressions. Worker/specialist-reported real-browser geometry/focus runs were not duplicated here. Full-App testing in progress is not represented as completed by this verdict. No source edit, broad test, Cargo/native build, actual user UI, private data, network or `uv` operation was performed.

The initial `5030a75c` general review below found no additional issues beyond the three separately owned React/TypeScript P2 findings. Its pending disposition is superseded by this closeout.

## General/security conclusions

- Panel entries are derived from work-group event steps, within the existing user-turn grouping. Original message indices are passed to action callbacks, so branching still targets the source answer. `Conversation` is keyed by active session ID, resetting panel/open-detail/scroll-local state at a session boundary. No new persistence, cross-session store, backend request or authority-bearing payload was added.
- Permission questions remain outside the activity panel, keyed by session and question ID, and answer through `controller.answer(active.id, ...)`. Panel expansion, closing and Escape handling do not approve or retry a tool. Tool execution permissions and native/backend dispatch are outside and unchanged by this commit.
- Tool commands, outputs, descriptions and parsed diff rows remain React text children/preformatted text. No raw HTML, eval, dynamic execution or new URL-opening surface was added. Existing protocol secret masking/output bounds and safe Markdown rendering remain the input boundaries; this commit does not bypass them. Public panels do not expose previously private protocol fields.
- The first two activity rows and the bounded all-entry pane implement the intended per-turn tool aggregation. Narrative/final answers, tasks, change summaries, preview/plan cards and retry callbacks retain their existing rendering paths. Thinking-detail loss is resolved through explicit-preference disclosures. Verbose/summary view behavior is explicitly retained rather than silently changing permission or data ownership.
- Wheel containment, native non-passive listener cleanup, keyboard Escape isolation and local expansion state are bounded to the panel instance. The new auto-follow pause does not mutate messages or ownership. Automatic-focus and geometry findings are closed by their final bounded corrections and focused browser regressions; native viewport acceptance remains separately owned.

Independent commit whitespace checks passed. Read the changed source, existing panel/unit/browser tests and immediate protocol/card/hook consumers. Worker-reported focused Vitest/browser/full-App results were not duplicated here; no broad test, native build, Cargo, `uv`, real user UI, private chat, network, model or secret access was performed. The eight typography snapshot updates reflect the changed closed-history rendering; this review does not claim a new font change or fresh full-suite success.

## Review Summary

| Severity | New findings | Existing tracked findings |
|----------|--------------|---------------------------|
| CRITICAL | 0 | 0 |
| HIGH | 0 | 0 |
| MEDIUM | 0 | 0 |
| LOW | 0 | 0 |

Verdict: APPROVE at `897cf4fc` — all tracked P2 findings, including the independently reproduced WebKit focus continuation, are resolved; no additional actionable issue established in this bounded general/security scope.

# Fusion continuation — 25 September 2026

## Release decision

**Not accepted.** The installed Fusion app remains at runtime 0.4.5 and was not replaced. No DMG or GitHub release was produced. The positive authorized stock-import path, packaged macOS experience, live voice hardware, and ChatGPT comparison have not passed acceptance.

## Source changes

- The Next route verifier now rejects a POST route whose only return is 401/403. It flags the sixth isolated GATE artifact, where every import request was denied despite five passing negative tests.
- The verifier also flags a literal session-secret fallback and a localhost Origin exception independent of the request Host. Both were observed in the seventh isolated attempt's `lib/session.ts`.
- The composer requests the model catalogue with its current workspace mode. In coding mode, verified web sessions that have not passed the mutation tool evaluation are omitted. Chat mode retains them for conversation.

## Seventh isolated long-task attempt

The clean `fusion-eval-gate-seventh` worktree started from GATE commit `66b05da`. It did not copy `.env` or contact the live stock service. The first invocation was blocked before any model call because the user's persisted strict selection was `chatgpt_web/main/auto`, whose mutation tool evaluation had not passed. A second invocation used an in-memory reset to the NIM apprentice; it consulted Gemini and wrote partial `types.ts`, `stokApi.ts`, and `lib/session.ts`, then the execution session disappeared without a final result. A continuation likewise disappeared after read/search calls. Neither run is an acceptance pass. The partial session helper has the two verifier findings described above. The isolated files were not copied to the user's GATE checkout.

## Verification

- Focused Python tests for model catalogue and Next route verifier: passed.
- Ruff repository check and mypy over 327 source files: passed.
- React: 712 tests across 93 files passed; production source build passed.
- The full Python suite passed on the final source tree (four existing skips and one upstream deprecation warning).

These checks establish source regressions and blocking findings. They do not establish a functional authorized import or packaged-app readiness.

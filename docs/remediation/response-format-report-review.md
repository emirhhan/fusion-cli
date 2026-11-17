# Verification reports preserve explicit reply formats

Date: 2026-11-05

`_apply_turn_report` previously prepended a prose verification report to every
changed-file response, including otherwise valid JSON that the user explicitly
requested. It now retains the authoritative `completion_report` while preserving
successful strict-format responses. Verification summaries and real change lines
are published separately through the existing events, even for non-streamed
answers. Ordinary prose keeps its existing report rendering.

Format recognition is conservative: direct affirmative JSON/result-only
instructions are recognized, while quoted examples, negative directives,
JSON file targets/content instructions and ordinary JSON explanations are not.
Later explicit negations override earlier format requests. It does not invent
values, populate a requested schema or extract numbers from generated prose.
Result-only handling prevents extra harness prose; it does not claim to correct
an already verbose model answer or enforce an arbitrary number of lines.

For requested JSON, blocking verification replaces an untrusted model success
with an explicitly identified Fusion error object containing bounded actual
completion evidence. Invalid generated JSON, code-fenced JSON, trailing prose
and non-JSON constants produce a format error rather than fabricated result
fields. Thinking removal remains in effect. Failed turns cannot become
successful through this presentation path.

Twelve initial regressions and three additional edge cases failed before their
fixes. Late-platform/PR-disclosure regressions then proved that those handlers
could append prose after report formatting. A final format check now runs after
both handlers and before answer publication. It rejects a mixed JSON/prose reply
instead of stripping the warning back to a false success; the appended warning
is retained in bounded, redacted error details. Rechecking an existing Fusion
error is idempotent. Evidence events are still published only at report creation.

The final six-file response/completion/evidence/report/PR/platform test run passed
all 99 tests. Ruff check/format and mypy on both production modules passed.
Independent Python/general reviews remain with the parent. Fixed-line formatting
and correction of a model's verbose result-only answer are outside this bounded
presentation fix; neither is claimed to be solved by number extraction.

## Final protocol boundary follow-up

Actual `run_agent` → `TurnAnswered` → `ProtocolSink` tests exposed two additional
places that mistook valid JSON string data for instructions: the integrity
heuristic retried a literal `FUSION_TOOL_CALL`, and the visible leak/thinking
filters could remove literal marker or `<think>` data. The shared
`clean_requested_response` now validates explicitly requested JSON before
thinking removal, also preserving inner markup when a real leading thinking
envelope precedes the JSON. Normal prose retains its original filtering.

Only the integrity heuristic is skipped for complete, non-truncated, explicitly
requested valid JSON. Real action evidence, pending todos and local-mutation
continuation gates remain active. Regression tests cover each boundary, including
an unperformed file mutation that must still fail and a truncated response that
must still be repaired. JSON data is never dispatched as a tool call.

The final eight-file regression run passed all 134 tests. The output-format file
also covers bare JSON filenames and explicit negative format requests, alongside
positive controls. Independent review of real provider streaming remains separate
from these non-streamed application-protocol checks; an all-path streaming
guarantee is not claimed here.

Independent review found a further file-content distinction: quoted destinations
and non-JSON filenames such as `result.txt` must not request JSON chat output.
Quoted file references now become neutral object tokens, without reintroducing
quoted instructions. Destination binding handles generic filename extensions;
an explicit reply target still takes precedence. Five new negative regressions
failed before this fix, and two positive reply-format controls were added.
The final eight-file run passed 141 tests; Ruff and mypy checks passed.

Continuation review found a real scope mismatch: `devam et` inherited mutation
requirements but lost the original response format. A cosmetic intro could then
consume an otherwise valid tool response, and later report text could prefix the
requested JSON. Response formatting now reuses the existing `effect_request`
binding through `effective_response_task`, accepting only genuine user messages.
The bound request is used for the intro, final-text cleaning, integrity check,
completion report, late-disclosure guard and visible answer. Tool routing keeps
its existing current-task behavior. New unrelated requests do not inherit an
older format; harness notes and synthetic summaries cannot supply one.

Two actual-engine continuation regressions failed before the fix. They now write
the requested file and return valid JSON with literal tool markers and thinking
tags preserved, in exactly two model calls with no cosmetic intro. Repeated
continuation and unrelated-task/harness/summary controls also pass. The final
eight-file regression run passed 147 tests (18.88 seconds); Ruff and helper mypy
checks passed. This change does not alter action-evidence requirements.

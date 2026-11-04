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

# Aggregate budget for automatic teacher phases

Automatic preflight planning could wait for two 300-second attempts, then start a
new format-repair question with another two attempts. Final review added another
independent wait. A real code-repair acceptance run completed in 178 seconds,
with automatic teacher work dominating the elapsed time.

`runtime.teacher_auto_phase_timeout_s` is a positive, finite timeout, default 30
seconds. One monotonic deadline is shared by every attempt and format repair in
an automatic plan phase, or by the attempts of an automatic final-review phase.
An authoritative outer turn deadline may further reduce that phase to one quarter
of the remaining turn time, leaving room for main work and delivery. Per-request
provider timeouts are not treated as remaining turn duration.

Expiry produces an honest activity status and skips that advisory phase. It does
not globally mark the teacher unavailable or disable subsequent direct calls.
Ordinary main execution, self-review and deterministic verification gates retain
their existing behavior. User cancellation propagates after cleanup, including a
provider that suppresses cancellation or converts it to TimeoutError. A late
response cannot publish a teacher plan or apply its todos. Cancellation cleanup
is awaited: the budget is a work deadline, not a guarantee that uncooperative
cleanup finishes at the same instant.

The actual direct/model-initiated `ask_teacher` path remains unchanged. It uses
`request_timeout_s` (bundled default 600 seconds) and its existing candidate-chain
policy, rather than the automatic wrapper's `teacher_timeout_s` (default 300).
No user config is rewritten. Zero, negative, Boolean, NaN and infinite automatic
timeouts are rejected in loaded and programmatic config; existing disabled teacher
or unavailable session behavior remains the way to disable advisory access.

Five actual automatic-phase/cancellation regressions failed before changes. The
final eleven-file teacher/manual-tool/budget/config validation passed 203 tests in
24.34 seconds. Ruff check/format passed; full changed config-model/loader and
teacher-flow mypy passed. Tests cover shared retry/repair deadlines, slow cleanup,
real cancellation and converted cancellation, final review, authoritative deadline,
manual request-timeout isolation, defaults and invalid values. Independent
Python/general review and any application build remain pending.

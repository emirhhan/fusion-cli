# Bounded deliverables and automatic teacher consultation

The user wants reliable completion without the unnecessary planning and review
latency observed in the live counter task. On pinned `dd9332d5`, GUI-equivalent
NIM selection completed the working counter in 144.638 seconds with automatic
teacher consultation and 44.295 seconds without it. Both artifacts passed
independent real Chromium interaction checks. This is one paired task, not a
general model benchmark.

## Chosen approach

Keep teacher configuration and the `ask_teacher` tool. Recognize a conservative
structural exception: a short, explicit single-file, self-contained deliverable
with no external dependencies. Multiple file references, explicit integration
or teacher requests, and ambiguous scope retain the existing teacher workflow.
This exception avoids the automatic preflight plan; it is not permission to
ignore the task, skip tools, or claim unmeasured behavior.

For a successful bounded change that actually affected one source file, avoid
the second automatic teacher review only when ordinary self-review is eligible.
Extract the existing eligibility conditions once and use them both before the
teacher decision and after any teacher correction. Explicit `self_review=False`
therefore retains teacher review. Deterministic verification and its failures,
ordinary review completion/failure events, budgets, and correction behavior stay
in place.

Global `teacherless=True` was rejected: it also hides voluntary consultation.
Skipping teacher review using only the configured self-review flag was rejected:
an explicit override or structural exclusion could leave both reviews skipped.

## Verification plan

- Reproduce the measured single-HTML request as a classification regression.
- Cover another file language and reject multi-file, API, integration, explicit
  teacher, absent self-containment, long, and numbered multi-step requests.
- Execute real file tools through the engine with a scripted provider: no
  automatic teacher call, one ordinary review, and deterministic verification.
- Prove voluntary `ask_teacher` remains offered and executable.
- Prove explicit ordinary-review disable retains teacher review; multiple actual
  changed files do not qualify for duplicate-review removal.
- Keep verifier failures visible and preserve ordinary-review eligibility for
  existing budget, workspace, remote-only, and override cases.

Product changes are confined to teacher planning/flow, one review-policy helper,
and the approved loop teacher/self-review eligibility region. New live acceptance
will run only after review of these changes.

## Implementation evidence

The initial regression run exposed eight bounded-policy failures; the new
eligibility helper's fourteen cases also failed before implementation. After
implementation, all 35 new cases passed. The relevant teacher, loop, narration,
review, artifact, and research regression run passed 268 tests, with one existing
Pydantic warning. Ruff check/format and mypy on the three policy/flow modules
passed. Independent review and post-change live acceptance remain separate gates.

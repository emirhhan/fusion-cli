# Optional self-review respects the remaining turn deadline

The actual configured-default `7ba36a26` report run finished all seven verifier
stages by 287.351 seconds, then began optional self-review with only about
12.6 seconds left in its 300-second task budget. The review's normal 20-second
provider timeout and 22-second outer timeout ignored that remaining time. The
outer task deadline cancelled the whole invocation and returned a generic
deadline failure instead of the already measured report. That historical run
remains failed; an independently usable artifact does not retroactively make
its engine result successful.

The fix is confined to optional feedback scheduling in `loop.py`. It takes the
smaller remaining limit from the original external deadline and shared hard
budget, reserving one second for normal result finalization. When no feedback
time remains, no reviewer starts. Otherwise feedback preparation and the review
await share that bounded window. A local timeout or skipped review publishes the
existing `SelfReviewFinished(completed=False)` event and retains the original
outcome. No clean reviewer verdict is invented. Without a hard deadline, the
existing configured review timeout remains authoritative.

External cancellation still propagates. Actual findings still enter the normal
correction flow and require its normal verification; existing failed outcomes
remain failed. Mandatory verification, Stop hooks, model preferences, configured
judge/teacher timeouts and hard deadlines are unchanged. The one-second reserve
is not a guarantee against arbitrarily slow filesystem operations, mandatory
hooks, learning or cleanup; those paths may still exhaust the real deadline.
This change does not suppress their cancellation or claim they succeeded.

## Verification

Eight focused controls pass, including a real `run_agent` finish flow that writes
and reads an owned file, produces typed passing evidence, reaches the near-end
deadline, and returns its verified report plus final answer before the outer
timeout. Other controls cover both hard-limit sources and their precedence,
stalled-feedback cancellation, preserving an existing failure, external user
cancellation and an ordinary completed review without a deadline.

The same corrected controls were run against the immutable `7ba36a26` source:
six fail and two cancellation/compatibility controls pass. Initial QA attempts
used a wall-clock timeout covering cold startup, then a summary-only fake gate
and a streaming-provider publication assumption. Those QA failures were retained;
the corrected baseline uses a timeout armed by the measured verifier, actual
file-content evidence and a buffered scripted provider. No historical live run
or source pin was changed.

Final selected regression: **204 passed, 1 existing Pydantic warning, 41.12 s**
across deadline, review, eligibility, completion, main agent, verification and
shared-budget suites. Ruff and formatting checks pass on the two changed Python
files; mypy passes for the source module. No full repository suite was rerun in
this bounded worker task; parent integration verification remains separate.

Evidence directory:
`/Users/motogate/Documents/Codex/2026-11-04/fusion-u-a-ve-bir-kullan/work/reliability-v2/optional-review-deadline-v7/`.
No live model, provider, native UI, network service or dependency installation
was used. The original checkout and bundles were not modified. Independent
Python/general review and a later real-task acceptance are still required.

# Independent probe uncertainty

A silent primary request can occupy a provider's concurrency slot while a separate
health probe queues behind it. Timing out that probe does not establish whether the
primary is dead, queued, or still working.

The reviewed source `628c06dfb65a0e49b8b7c3aab67339816e2fb98a` classified the
probe's 30-second timeout as server unhealthiness. `watch()` returned a failure
string, and `_consume_with_liveness()` cancelled the primary and entered the retry
path. The pinned acceptance trace recorded this message for case A at elapsed
122.549 seconds and case B at elapsed 330.804 seconds. The relative trace is
`work/reliability-v2/final-user-acceptance/runs/reviewed-628c06df/public-trace.jsonl`
in the task workspace; its `provenance.json` identifies that pinned source.

`ping_for()` now distinguishes three outcomes:

- `None`: the server answered successfully or reported rate limiting/overload.
- A failure string: a concrete failed response or confirmed connection failure.
- `UnknownHealth`: probe timeout, timeout reported as a provider result, missing
  result/error detail, or an exception without a confirmed transport diagnosis.

An unknown result keeps the primary alive and schedules the existing recheck.
It does not mark the primary healthy and does not set `unresponsive_reason`.
The primary's configured request deadline (including the existing 600-second
configuration), outer call/turn budget, idle limits, and user cancellation retain
their existing authority. No deadline is extended by a probe. If a primary chunk
arrives while a probe is pending, that direct evidence overrides the independent
probe failure. Concrete failures still use the existing cancellation/retry path.

Controlled tests hold a concurrency slot with a primary, let its queued probe time
out, and then complete the primary successfully. They also exercise serialized
probe timeouts, empty probe streams, local probe errors, repeated unknown probes
ending at the primary deadline, cancellation cleanup, concrete connection failure,
and a primary chunk arriving during the probe. These tests establish a finite
client cancellation bug; they do not establish that the real NIM primary requests
in cases A/B would have succeeded. Provider availability remains unverified.

The probe already has `CompletionRequest.max_retries=0` by default and an empty
provider retry schedule. Its reasoning settings are unchanged by this fix.

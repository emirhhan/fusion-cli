# Automatic recall diagnostic v1

Purpose: obtain native cause evidence; no runtime cause is established by local success.
One terminal AutomaticRecallDiagnostic event per recall_hints invocation, emitted on
its owning event loop, using ProviderCallDiagnostic's ProtocolSink exclusion.
TraceWriter retains and replays it. No chat/UI/tool/prompt payload changes.

Worker owns only a private progress collector and request. A ContextVar read scope
records bounded operation/phase/count/error-class snapshots at existing count/query
calls, without extra queries. Timeout snapshots in-flight work without worker callbacks
into publisher/deps. Cancellation propagates, emits cancelled locally, and retains
single daemon admission until the worker exits. Late completion emits nothing.

Fields: literal source_version, status, phase, backend_operation, error_class category;
memory_kind (none/null/chroma/other), inferred from known concrete types without opening memory;
elapsed_ms (bounded), returned_count (0..2), formatted_count (0..2), count_result
(0..1,000,000; null when unknown). No task, lesson text/IDs, paths, arbitrary errors,
keys, or verification claims. Correlation uses the existing Event envelope.
Terminal states distinguish disabled flags, no memory, exhausted budget, admission
busy, timeout, cancelled, backend error/lock/cooldown, empty, format rejection,
stale owner, offer observer failure and offered. Backend status snapshots remain
separate from terminal status so a timeout can identify count/query lock/backend phase.
Diagnostic publication failure is swallowed independently from optional hint delivery.
Existing deadlines, two-lesson/4096-character limits, ownership and rollback stay intact.

# K23 optional original-trace writes

Optional trace append no longer uses the default asyncio executor. A dedicated
mutation worker allows one actual daemon thread for this subsystem and no queue.
Busy callers return false. The permit remains held until the real worker exits,
including after a caller timeout or cancellation. Optional reads continue to use
their separate read-only worker; it is never used for mutation.

The caller waits at most one second by default and cancellation propagates.
Deadline and ownership are checked at admission, worker start, after staging,
and immediately before publication. Ownership includes the original scope,
journal path, shared epoch object and captured clear generation. Live handles
with the same normalized application path share this epoch without a growing
global path cache.

Append validates and redacts the original segment, reads the existing validated
trace under its file lease, then releases that lease. It stages the complete
replacement in a unique 0600 file beside the target and flushes/fsyncs privately.
The serialized total retains the existing hard 2,000,000-byte trace cap. It never
truncates older segments to admit a new one. Scope, complete tool-call grammar,
call-ID conflicts, strict decoding, owner hashes and secret redaction remain
required. A different owner cannot replace a trace at the same path.

Final publication acquires the shared per-path mutation lock and file lease,
checks that the existing validated records are unchanged, rechecks ownership,
and atomically replaces the trace. A concurrent change fails closed instead of
overwriting another writer. Clear invalidates the shared generation immediately
and takes the same publication lock before its existing leased deletions. A
staged worker from an older generation cannot publish after clear completes.

These guarantees have deliberate OS limits. A filesystem replace already entered
cannot be interrupted by Python cancellation. It may finish after a caller has
timed out or cancelled; false means capture was not confirmed, not physical
rollback. Synchronous clear waits for an already admitted publication, then
deletes it. Clear is not claimed to have bounded latency, and its existing file
lease failure behavior is unchanged. A stuck staging syscall retains the one
daemon/permit; cleanup occurs when the syscall returns. Process death may leave
a private redacted temporary file. Directory-fsync durability and cross-process
clear generations are not newly guaranteed. Broader snapshot I/O and cumulative
task-level I/O budgets remain separate work.

Regressions block real staging fsync to verify bounded wait, cancellation,
cross-handle clear, owner changes, no queued worker, unchanged prior trace,
temporary-file permissions and cleanup. An entered atomic-publish test verifies
that clear cannot return before serialization completes and that no trace
remains afterward. Size, malformed content, idempotency and privacy coverage run
with the existing journal/read regression suite. Experimental flags and persisted
settings remain unchanged.

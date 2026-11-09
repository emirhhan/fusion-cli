# K22 native failure classification and bounded recovery

Historical K22 requires real measurements of the action-time causes and method
cost of AX refusals. This source change adds diagnostic collection and bounded
recovery advice; it does not close that live acceptance requirement.

Previously only complete-tree, unique-target fingerprint failures entered the
native recovery path. Other failures lost their machine-readable cause and
eventually received generic advice to try different arguments. Inspection
failures did not enter native recovery at all.

The trusted background inspect/action boundary now retains fixed cause metadata
and measures elapsed wall time around the actual helper invocation. Time includes
helper startup and any helper preparation, rather than measuring AX execution
alone. Each sample is clamped to 0–600,000 milliseconds. Caller-supplied timing
fields and native response timing fields are ignored. Original visible errors,
native guard booleans and value-kind diagnostics are preserved.

Complete native guard booleans classify tree truncation, nonunique identity,
fingerprint change and path/identity mismatch in that order. Fixed native error
messages classify missing permission, missing/unverified windows, unsupported
AXPress/AXValue, unverified writes and rejected AX operations. Other errors
remain explicitly unknown. Partial or malformed guards do not prove a cause.

Only dispatched builtin functions supply recovery receipts; same-named remote
or replaced tools cannot supply native evidence. Cause totals retain exact
PID/window, operation, attempt count and accumulated helper-boundary time in the
per-drive recovery state. Cause keys and stale-target episodes are each bounded
to 256 entries, evicting the oldest key when full. Labels, input values and full
native references are not retained in those totals. Existing drive/tool budgets
continue to bound execution; this change introduces no automatic retry.

Permission failures, ambiguous/incomplete targets, uncertain writes and unknown
outcomes receive conservative fixed advice, with no keyboard or coordinate
fallback. An unverified write explicitly warns that the operation may already
have happened and requests read-only result verification. Unsupported operations
are distinguished from stale references. Existing unique-tree stale feedback
retains its separate method-change threshold. All policy, approval, current
PID/window, reference uniqueness, fingerprint/path and visual-grounding checks
remain in force.

Synthetic regressions cover the cause matrix, measured duration provenance,
guard preservation, real-loop action/inspection feedback, replaced/remote-tool
rejection, and bounds on both state tables. Actual GUI action-time measurements,
method comparisons, matching native package acceptance and provider-based
behavior checks remain outstanding. No settings, flags or native Swift source
were changed.

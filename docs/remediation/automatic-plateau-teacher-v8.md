# Automatic recovery after productive reading

The real `configured-default-da761-C-v7` run completed directory discovery and
four successful file reads, then automatically consulted the teacher for about
108 seconds. The main model did not request that consultation. The recovery
helper used `request_timeout_s` (600 seconds) instead of the automatic advisory
phase cap (30 seconds). The task edited the form at 288 seconds but reached its
300-second deadline before browser verification and delivery. That run remains
failed; its independently checked artifact is separate evidence.

The count-only exploration reminder no longer becomes a stall reason. Automatic
recovery still uses existing repeated-error, repeat-guard, same-output and stalled
signals. The reminder allows necessary targeted reading to finish and only
suggests teacher consultation when one of those signals exists. The fallback
question describes the actual stall without assuming a multi-file task.

Plateau recovery uses the existing automatic-phase deadline policy. Its one
deadline is capped by `teacher_auto_phase_timeout_s` and a quarter of any actual
remaining turn deadline or shared hard time budget. No per-request minimum
inflates a short remaining budget. An expired phase starts no tool. Attempted
consultations retain correlated tool records; timeout or late success is a failed
advisory result and cannot enable teacher takeover. Existing phase-expiry status
explains that work continues from current evidence. External cancellation
propagates even if the tool converts it to a return value or timeout.

The direct/model-initiated `ask_teacher` tool, its configured request timeout,
candidate policy and explicit user instructions remain unchanged. No new tool,
model preference, mutation allowance, context cap or call threshold was added.
The previous optional-self-review deadline fix remains byte-for-byte unchanged.
The caller's teacher availability, teacherless, depth, capability and allowed-tool
conditions remain intact.

Validation used the original interpreter and `PYTHONPATH=src` in the isolated
worktree. The corrected new regression module against immutable `da76120e`
produced **10 failures and 5 passing controls**. Against the changed source,
the eight selected modules produced **225 passed**, with one existing Pydantic
warning. They include the actual five-read-then-edit flow, true stall signals,
automatic timeout/short or expired deadlines, delayed cancellation cleanup,
external cancellation, existing direct-tool timeout policy and the previous
self-review deadline tests. Ruff, formatting and mypy on the owned source passed.

Evidence is under
`work/reliability-v2/automatic-plateau-teacher-v8/` in the task workspace. The first
productive-flow test wording was classified as a read-only request; its preserved
failure was not used as the final causal proof. The corrected request performs
the edit on the old source and fails specifically because of the unnecessary
consultation.

Cancellation waits for cooperative cleanup. This does not guarantee termination
of arbitrary cancellation-ignoring tool internals or bound their independent
side effects; late returned advice is rejected. No real provider, network,
desktop action, installed app, original checkout or runtime bundle was exercised
or changed by this fix. Independent review and real task acceptance remain
required.

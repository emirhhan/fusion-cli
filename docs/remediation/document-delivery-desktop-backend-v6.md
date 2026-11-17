# Desktop document delivery: backend

The desktop adapter can separate the exact generated verification prefix from a
verified, successful short static report. It keeps the engine outcome, CLI
rendering, permissions, verification decisions and global HTML classification
unchanged. Explicit reply formats and requested evidence/audit details retain
their original response. Warnings, failed or missing measurements, false claims,
job deliveries, test tampering, budget stops, unknown prefix composition, wrong
output targets and inconsistent execution binding prevent compact presentation.

`present_delivery` supplies the original model text and a version-one public
`kanit` envelope. Optional fields are `sunum: document`, `kontroller`,
`olculmeyen`, `oneriler`, `degisiklik_ozeti` and `ayrintilar_kisaltildi`. Detail
strings are redacted and capped at 500 characters; checks, missing measurements
and advisories have ten entries each, change summaries fifty. The entire UTF-8
envelope is limited to 32 KiB. Optional detail tails are removed first. Paths
are kept whole or omitted, never shortened into another openable filename;
original totals and truncation flags remain. Malformed critical flags, failed
criteria hidden beyond a list cap, unsupported versions and invalid Unicode do
not become successful document cards.

The accepted transcript owner is captured with `SubmissionKey` before admission
lookup/claim awaits. Completion writes clean text and proof together in one
existing `TurnAnswered` row to that captured store. Legacy `record_assistant`
still returns `None`; the new presented-write API reports persistence success.
Unknown ownership, tombstones and failed writes retain the original full-text
RPC presentation. Permission tightening after a completed write is best effort,
as with transcript-directory creation, so a chmod error does not duplicate an
already written answer. Replay uses the same public projection and existing row
and total-history limits. Completion metadata never enters model messages.

## Verification

Use the original environment with `PYTHONPATH=src`; no dependencies or providers
were invoked. `tests/test_document_delivery_presentation.py` covers adapter
output, exact-prefix and target binding, source outcome immutability, metadata
failure/cap/redaction cases, real AppSession dispatch and reopen, write fallback,
tombstones and admission/execution chat switches. Existing AppSession, submission,
auto-profile, transcript, visible-history, strict-format and teacher-policy
regressions are included in the targeted batch. Final selected run: **317 passed**,
with one existing third-party Pydantic warning; Ruff, formatting and mypy on five
source files passed. Results and wire fixtures are
under the task workspace's `work/reliability-v2/document-delivery-backend-v6/`.

The first adapter API was absent (RED). After correcting a test-only enum typo,
the actual AppSession test reproduced the full prefixed reply before adapter
integration (RED). A warning-report persistence fallback was independently
reproduced and fixed. Two test preconditions were corrected without changing
production semantics: an executing turn already rejects a root switch, and a
chat round trip can contain an older recovery notice, so completion-proof
identity is counted independently from unrelated notices.

## Separate accepted-context defect

The new presentation guard does **not** repair the existing execution lifecycle.
An owned offline reproduction proves that rebinding before `_run_turn` can give
the executor a new root and conversation; switching chat while personal-memory
loading is pending can also change its conversation. The guard refuses compact
presentation when the measured execution binding differs from the accepted
owner. The two desired-behavior tests remain RED in the task artifact
`test_admission_context_owner_repro.py` and `execution-binding-red.xml`; they are
not shipped as assertions that the faulty behavior is correct. Parent-authorized
accepted-context ownership work is a separate follow-up, required before final
goal completion. This change does not establish native UI acceptance or completed
model self-review.

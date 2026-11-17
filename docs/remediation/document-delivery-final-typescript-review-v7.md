# Final decoder review: scoped approval, integration hold

Integration update by the parent: the backend HOLD below records the earlier
`cb870fca` finding. Its `c6e63906` fix subsequently passed the independent
[Python review](document-delivery-final-python-review-v7.md) and
[general review](accepted-context-final-general-review-v7.md), including durable
replay and frontend checks. The original TypeScript findings remain unchanged
below for provenance; they do not describe the final backend verdict.

Frozen frontend: be7456d5b7adce1960919847e658af9a6604b98f.
Backend projection inspected: cb870fca. No product files changed by this reviewer.

## Scoped frontend APPROVE

The previous weakened-test metadata and excess criterion-total findings are fixed.
Known supplied tamper metadata is independently validated, unsafe or inconsistent
counts fail closed, suspicious findings downgrade verification to unknown, and all
supplied tamper envelopes exclude compact document presentation. Unknown future
fields remain ignored and absent old optional fields stay compatible. Nested
metadata is not echoed. Existing explicit warnings, failures, false-claim markers,
whole file paths, Unicode bounds, and delayed-history identity are preserved.

Validation: canonical TypeScript check passed; canonical `npm run lint:hooks`
passed; 174 tests across seven focused suites passed; 43 frozen independent checks
passed; six frozen production-source hashes still match; diff check passed.
An initial blanket eslint invocation failed on 37 existing e2e parser errors:
the flat configuration applies the TypeScript parser only to src, and the project
canonical command intentionally scopes eslint to src. Root instructed continuing
with the canonical command. No lint config was changed. Initial guessed activity
suite path matched no test; final seven-suite run used the actual Conversation
activity-panel suite, with its JSON result preserved as focused.json.

## HIGH integration HOLD: malformed known metadata laundered on replay

In appserver/delivery_presentation.py, explicit null for `criteria` (line131),
`criteria_status_counts` (line169), or `supheli_test_degisikligi` (line199) is treated
as absence. `ayrintilar_kisaltildi: null` is also silently removed. The frontend raw
decoder correctly returns invalid/blocking, but backend projection removes the
malformed recognized field and retains verified=true plus sunum=document. After
actual durable journal write/reopen the frontend consequently renders a verified
document. The null-list fix cb870fca handles uyarilar:null correctly, but these four
related known fields remain outside that guard.

This was proved through TranscriptStore.record_presented_assistant ->
load_visible_transcript -> actual frozen frontend historyMessages/decoder, using
only synthetic records in this review's own task directory. No provider, native,
network, or real user journal access occurred. Keep the integrated feature on hold
until absent-vs-malformed recognized-field semantics are consistent. Backend owner
and root were notified; frontend scope approval does not approve that backend.

Evidence: source-hashes.json, focused.json, independent-checks.cjs,
independent-results.json, replay-null-probes.json, crosslayer-null-results.json,
durable-replay-rows.json, durable-frontend-results.json, review-result.json.
All processes started by this review are terminal. No live handles remain.

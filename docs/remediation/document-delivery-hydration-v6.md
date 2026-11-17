# Delayed history overlap

The session reducer previously removed only same-text user rows when history
arrived after a live answer. The same stable assistant ID could therefore appear
twice, producing duplicate React keys and duplicate delivery cards.

`historyLoaded` now consumes an overlapping history row by message ID and role.
The existing live message keeps its position, nonempty answer and delivery proof.
History may fill a missing answer or proof. Unrelated history rows remain before
the live messages, including tool history, and separate stable receipt IDs remain
separate even when their text is identical.

Text matching remains only for user rows where at least one side has no stable
identity (absent or generated legacy/history ID). Generated IDs also require
matching text for identity overlap. Repeated old history loads remain idempotent
without treating equal text from distinct receipts as the same message.

Tests exercise the actual reducer and `historyMessages` decoder with clean-text
document proof, evidence-only rows, partial history, missing live body/proof,
distinct receipts, tool ordering, old rows and repeated hydration. Six regression
tests failed before the fix. All 97 focused store, history, identity, decoder and
card tests passed afterward; TypeScript checking and `git diff --check` passed.
No provider, model, native app or network calls were used. The change is limited
to delayed history merging; message submission and history replacement contracts
remain unchanged.

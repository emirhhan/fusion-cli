# Independent Python review: automatic teacher advisory phase budget

Reviewed immutable snapshot: `10721cc8`, including source `f023b8a5`,
deterministic fixture follow-up `ab6502ce`, and slow-context control `e656b1d2`.
Concurrent generic research policy changes were excluded.
Verdict: **APPROVE**; no HIGH/CRITICAL findings in this finite Python scope.
No production source edited by the reviewer.

The new positive finite automatic-phase timeout defaults to 30 seconds and is
validated in both loader and programmatic dataclass paths, including zero,
negative, NaN/infinities and bool rejection. Plan attempts and format repair share
one monotonic deadline. Only an authoritative turn deadline can shorten that
phase to a quarter of remaining time; a provider request timeout cannot do so.
The final automatic review uses its own phase budget. Exhaustion is visible and
does not set the global teacher-unavailable flag or apply late plans/todos.

Timeouts are cooperative: async provider cleanup is awaited and pre-request
context/diff work runs in threads. The phase accounts for that elapsed time and
will not start a provider call after expiry, but it is not a hard 30-second wall
limit on noncooperative provider cleanup or an individual filesystem/thread
operation. The implementation and approval must not be presented as such a
hard guarantee. Genuine user cancellation remains CancelledError, including when
a provider swallows it or converts it to TimeoutError without clearing the task's
cancellation count; normal deadline cancellation is not confused with user cancel.

The explicit/model-invoked ask_teacher tool retains its existing request policy.
An independent test exercised the actual registry/engine_tools/provider path
with automatic and advisory timeouts both set to 0.001 seconds, a provider that
took 0.03 seconds, and request_timeout_s=600.0: it succeeded and the actual
CompletionRequest carried timeout_s=600.0. This is an observed request policy,
not a claim that a provider was left running for 600 seconds.

## Verification

- Ruff passed for loader/models/teacher_flow and the new phase-budget test file.
- Mypy passed for the three source modules.
- Frozen-source suite: **131 passed in 14.09 seconds**, covering phase budgets,
  retries/format repair, cleanup/cancellation, actual ask_teacher calls, config
  validation, teacher startup and three external general wrapper controls.
- Independent actual 600-second manual request-policy control: **1 passed in
  0.60 seconds**.
- Suite log: task workspace
  `work/reliability-v2/python-auto-advisory-pinned10721.log`.
- Independent control: task workspace
  `work/reliability-v2/test_python_manual_teacher600.py`.
- Terminal session 26501 completed exit 0; no reviewer sessions remain active.

SHA-256 fingerprints at the pinned snapshot:

- `config/loader.py`: `3644927922d621e4f3185fb4e192fde66d443a4b04a2ac22b1f9b3f7f7808d99`
- `config/models.py`: `574c7d5c9d890baf89e969c5b780d492b30ac3e75e9731c049b95941fbd2de62`
- `config/defaults.yaml`: `c3587d97dbe92401f5b2b7657dc2c5e9773efbd4c3734852d0940e1d37d69da4`
- `agent/teacher_flow.py`: `2aee436337736940baa5a83a7b7e0719f2b3a848e16e822632d30ae962a5e018`
- Unchanged explicit tool path `agent/engine_tools.py`:
  `96830eafc4672990a94807c8aea561e5b8811eaf014057897ee7e8c59c9f6cb8`

No original checkout, installed app or package mutation occurred. Contact probe
and concurrent generic research changes are outside this approval; prior contact
classifier/security approvals retain their own independent scope.

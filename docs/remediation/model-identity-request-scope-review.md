# Model identity follows the actual request

Date: 2026-11-05

The agent previously inserted `identity_hint(config.agent.model)` while assembling
its initial system prompt. Task mapping, capability selection, escalation and
active overrides can choose another provider model later. The actual request
could therefore tell model B that it was model A.

The identity hint now refreshes at `_call_model`, using the same resolved, live
`ModelSpec` that builds the provider. Selection is not repeated and routing is
unchanged. A reserved suffix in the primary system message is replaced between
requests; custom system text and user messages are retained. Repeated requests
do not accumulate identity hints or extra system messages.

A fallback chain sends the same request to multiple possible provider leaves.
Before the response, the engine cannot truthfully identify which leaf will serve
it. These requests name the requested primary and explicitly state that the
serving model is not yet confirmed. Strict mode can still have an availability
fallback, so it receives the same qualification. Actual result metadata continues
to report the serving model; the change does not rewrite generated answers or
pretend to infer their model from their prose.

## Validation

Four request-capture regression tests failed before the implementation. Five now
pass, covering mapped/default disagreement, an active override, fallback identity,
repeated calls and requests that initially have no system message. They exercise
the real request-construction path with only the provider boundary substituted.
Existing identity-hint and prompt-manifest tests also passed (13 tests before the
additional no-system regression). Ruff check, Ruff format check and mypy on
`loop.py` passed.

The broader ten-file regression run had one failure in the existing two-second
timing test
`test_agent_loop.py::test_hazirlik_bosta_kalma_penceresini_yese_de_model_cagrisi_kesilmez`.
Its isolated rerun timed out during `learning_steps.finish_learning` while awaiting
`asyncio.to_thread(settle_advice)`. This failure is retained; neither its timeout
nor its assertions were weakened. A complete repository test pass is not claimed.

Python and general code reviews remain pending at this handoff.

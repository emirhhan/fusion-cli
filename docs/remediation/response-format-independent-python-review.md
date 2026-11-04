# Response formats: independent Python and general review

Reviewed chain: `ceaa5117`, `f5944835`, `63cd3aec`, final correction `d49d1340`.

**APPROVE the scoped response-presentation changes.** No HIGH or CRITICAL issue remains in the reviewed helper and its report/final-answer/integrity branches. Teacher-policy branches were reviewed separately through `d3049307`.

The initial review reproduced and required corrections for valid JSON string data containing thinking tags, direct negated output-format requests, bare and quoted file-content destinations, and the quoted-filename/Turkish-dative placeholder separator. The final source preserves these data and intent distinctions. Both direct positive reply-format requests and ordinary prose controls remain intact.

Requested valid JSON is kept separate from prose verification reporting; evidence remains available through the authoritative completion report and existing events. A failed gate cannot be promoted to a model-generated success object. Invalid JSON and late appended disclosures produce explicit Fusion error JSON rather than invented result fields. Reapplying an existing error remains idempotent. Result-only handling preserves model text; it does not extract arbitrary numbers or promise to repair an already verbose model answer.

The complete-valid-JSON exception affects only the generic integrity diagnosis. Actual truncation, action evidence, pending todos and required local mutations still use their normal gates. Literal protocol-marker words inside JSON are data and do not dispatch tools. Ordinary prose still uses leak filtering. Genuine leading reasoning outside JSON is removed; thinking-tag markup inside a JSON string remains unchanged.

## Independent evidence

- Final negative/positive/file-destination/literal-data/failed-gate probes passed.
- Ruff passed for the helper and test module; mypy passed for the helper and `loop.py`.
- **60 tests passed in 5.32 seconds**: 57 response-format cases plus three independent streaming probes.
- The independent probes used the actual `EventingProvider` wrapper and `ProtocolSink`, splitting JSON into four-character chunks. `FUSION_TOOL_CALL`, `FUSION_PAYLOAD` and `<think>keep this</think>` values survived both final outcomes and concatenated serialized `TokenReceived` data. Each used one model call, no tool calls and no duplicate `TurnAnswered` event.
- The worker's nonstreamed application-protocol tests independently cover the accepted `TurnAnswered` path, including real file mutation and leading thinking envelopes.

Final log: task workspace `work/reliability-v2/python-response-review-final.log`. Exact source hashes: `python-response-teacher-approved-source-hashes.json`.

Historical failed probes are retained. The first external streaming-test invocation omitted the repository pytest configuration and failed async setup; rerunning with `-c pyproject.toml` produced two passing marker cases and the genuine thinking-data failure before the fix. After correction all three streamed cases passed, then passed again in the final 60-test run. Initial independent format tests also reproduced the negation and thinking-data failures rather than treating their later green results as proof that no bug had existed.

The reviewer did not edit production source. This approval is not a claim of exhaustive language recognition, provider-wide live acceptance, or completion of the full AI-quality goal.

## Follow-up: skip cosmetic calls for explicit compact replies

**APPROVE** the early `requested_response_format(task) is not None` return in `narration.intro_paragraph`. The check runs before building or calling the cosmetic provider and leaves normal introductions, invalid-intro filtering, tool execution and failure handling intact. Independent Ruff and mypy passed; **23 narration tests passed in 4.15 seconds**, including both new no-provider-call cases. Reviewed `narration.py` SHA-256: `b6f5f0fdd4fa6d4326165f76bfb141231931cf94f1bc2ec632e4290325b046ec`. Log: `work/reliability-v2/python-intro-format-guard-review.log`. Unfinished game-state changes were excluded.

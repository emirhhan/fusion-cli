# Evaluation Harness Profiles Implementation Plan

> Implement the approved three-profile arena benchmark while preserving current `fusion-full` behavior and keeping acceptance scoring independent.

**Design:** `docs/superpowers/specs/2026-08-27-eval-harness-profiles-design.md`

## Task 1: Establish profile contracts and metadata

**Files:**
- Create: `evals/profiles.py`
- Modify: `evals/metrics.py`
- Modify: `evals/report.py`
- Test: `tests/test_evals.py`

1. Add failing tests for stable profile values, default metadata, metadata JSON round-trip, and loading legacy reports without metadata.
2. Add `EvalProfile`, immutable `RunMetadata`, and optional metadata on `RunReport`.
3. Serialize metadata under a versioned top-level key while retaining the existing `results` and `summary` shape.
4. Run the focused report/profile tests.

## Task 2: Retain every repeated sample

**Files:**
- Modify: `evals/executor.py`
- Modify: `evals/runner.py`
- Test: `tests/test_eval_executor.py`
- Test: `tests/test_evals.py`

1. Add failing tests proving repeated executions receive `run-01`, `run-02`, and so on without overwriting transcripts or output files.
2. Extend the executor protocol with an explicit sample identity rather than a hidden mutable counter.
3. Pass repetition identity from `run_suite` through `AgentTaskExecutor` and preserve current single-run paths where backward compatibility matters.
4. Keep post-run acceptance execution rooted in the exact sample workspace.
5. Run focused executor/runner tests.

## Task 3: Add a safe system-prompt override for Minimal

**Files:**
- Modify: `src/fusion_cli/engines/agent/loop.py`
- Test: `tests/test_agent_loop.py`

1. Add a failing test showing an explicit system prompt replaces the canonical prompt while omission preserves existing behavior.
2. Add an optional keyword-only `system_prompt` parameter and thread it through `_initial_messages` without changing internal correction inheritance.
3. Run the focused agent-loop tests.

## Task 4: Implement Full and Minimal agent runners

**Files:**
- Modify: `evals/agent_runner.py`
- Modify: `evals/profiles.py`
- Test: `tests/test_eval_agent_runner.py`

1. Add tests locking Full dependencies to the current verifier, prompt, approval, and event accounting behavior.
2. Add tests proving Minimal uses its short protocol prompt, retains only required local file tools, disables verification and self-review, and uses a copied configuration with reflexion/lessons/playbooks/workflow disabled.
3. Refactor shared publisher/approval/dependency construction without changing Full output.
4. Implement the runner factory for both Fusion profiles.
5. Run focused runner tests.

## Task 5: Implement the one-call Direct runner

**Files:**
- Create: `evals/direct_runner.py`
- Modify: `evals/profiles.py`
- Test: `tests/test_eval_direct_runner.py`

1. Add extraction tests for one fenced HTML document and one raw HTML document.
2. Add rejection tests for commentary, multiple fences, missing/incomplete documents, and ambiguous output.
3. Add a provider test proving exactly one completion request, no tools, the configured primary model, verbatim artifact writing, event-based call accounting, and rate-limit propagation.
4. Build the provider through the existing factory and implement strict extraction with no retry or repair at runner level.
5. Run Direct/profile tests.

## Task 6: Add CLI profile and matrix orchestration

**Files:**
- Modify: `evals/cli.py`
- Create: `evals/matrix.py`
- Test: `tests/test_eval_cli.py`
- Test: `tests/test_eval_matrix.py`

1. Add parser tests for `run --profile`, its `fusion-full` default, and `matrix` arguments.
2. Add matrix aggregation tests covering success, calls, duration, Direct deltas, and partial non-rate-limit failures.
3. Construct every profile with one loaded configuration and profile-specific workspace roots.
4. Write one JSON report per profile plus `summary.json`; print a neutral comparison table.
5. Preserve the current exit code for rate-limit aborts and existing `compare` behavior.
6. Run focused CLI/matrix tests.

## Task 7: Independence and regression verification

**Files:**
- Modify as required: `tests/test_eval_agent_runner.py`
- Modify as required: `tests/test_eval_executor.py`
- Modify as required: `tests/test_evals.py`

1. Add/retain tests proving the EXIT_CODE criterion is absent from all prompts and verifiers and runs only after profile completion.
2. Run all eval tests.
3. Run full `pytest`, `ruff check src tests evals`, and `git diff --check`.
4. Inspect the diff and commit the implementation without staging root artifacts.

## Task 8: Real arena matrix evidence

1. Run the behavioral arena with all three profiles and `--repeat 3` into an explicit ignored/output directory.
2. Confirm nine sample workspaces and three profile reports plus the matrix summary exist.
3. Inspect failures and fix implementation defects; do not tune product prompts merely to improve the benchmark.
4. Re-run affected checks after any fix.
5. Report pass rates, mean model calls, mean duration, Direct deltas, model/provider identity, and any rate-limit caveat.

## Task 9: Continue the approved roadmap

After P0 evidence is complete, separately design and implement:

1. P1 browser-process lifecycle, timer/status/completion UX, environment setup repair, and structured `ask_user`/approval UI.
2. P2 measured command/control-panel gaps after auditing existing `/model`, `/agents`, `/skills`, `/mcp`, and `/providers` behavior.

Each subproject receives focused tests and full repository verification before being declared complete.

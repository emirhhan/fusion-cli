# Evaluation Harness Profiles Design

**Date:** 2026-08-27

## Goal

Measure Fusion's runtime harness tax on the behavioral arena with three comparable execution profiles:

- `fusion-full`: the current headless Fusion agent behavior.
- `fusion-minimal`: the smallest useful tool-using Fusion agent loop.
- `direct`: one provider completion with no agent loop or tools.

The benchmark must report behavioral success, model calls, elapsed time, and the deltas between profiles. A repeated run must retain enough evidence to audit every sample.

## Non-goals

- Redesigning the arena task or its behavioral acceptance command.
- Optimizing prompts based on benchmark results in this change.
- Enabling persistent learning or other stateful product features during evaluation.
- Implementing the P1 terminal/browser lifecycle work or the P2 command-information architecture work.
- Treating a Direct response as an agent action or silently repairing malformed Direct output.

## Fairness and Independence Invariants

All profiles use the same suite task, configured provider, selected model, seed policy, timeout, and post-run behavioral acceptance criterion. The acceptance command runs only after the profile has finished and is never inserted into an agent verifier, prompt, hidden criterion, or correction loop.

Each profile starts from an equivalent clean task workspace. Repetitions are isolated from one another. Persistent lessons, recall history, and product session state are excluded from every profile so earlier samples cannot influence later samples.

The scorer and report aggregation remain profile-neutral. Profile runners may create the requested artifact, but they cannot reinterpret or weaken the arena criterion.

## Profile Contracts

### Fusion Full

`fusion-full` preserves the existing `FusionAgentRunner` execution path:

- canonical Fusion system prompt;
- normal agent loop and registered local tools;
- normal Fusion verifier and blocking-correction behavior;
- configured self-review and reflexion behavior;
- real `ModelCallFinished` accounting.

It remains a deterministic headless benchmark profile: no interactive asker, no approval dialog, no persistent lessons, and no cross-run recall state. These exclusions must be present in report metadata so “full” is not mistaken for an interactive desktop session.

### Fusion Minimal

`fusion-minimal` keeps only what is required for a model to create files safely:

- the agent loop;
- base local file tools, including the canonical `replace_range` editor;
- a short system prompt describing the tool protocol and completion contract;
- real `ModelCallFinished` accounting.

It disables the normal verifier, blocking correction, self-review, reflexion, lesson recall, capability recall, project playbooks, and workflow augmentation. It must not mutate shared configuration objects to achieve this. Profile-specific dependencies and configuration are constructed explicitly.

### Direct

`direct` performs exactly one provider completion with no tools, agent loop, verifier, self-review, reflexion, or correction. It uses the same configured provider and primary model selection as the Fusion profiles.

Because the arena scores workspace files, the Direct prompt requests exactly one complete `index.html` document. The runner may materialize the response only when it is either:

1. exactly one fenced `html` block containing a complete document; or
2. a raw response whose first non-whitespace content is a complete HTML document.

The extractor writes the accepted document verbatim to `index.html`. Multiple fenced blocks, commentary surrounding a fenced block, a missing document, or ambiguous output are runner failures. The runner does not repair, merge, or retry malformed output. Provider usage is counted from the same `ModelCallFinished` event path; the expected count is one.

## Architecture

### Profile Selection

Add an `EvalProfile` enum with stable CLI values:

- `fusion-full`
- `fusion-minimal`
- `direct`

A runner factory owns profile construction. `AgentTaskExecutor` continues to own workspace snapshots and independent acceptance execution. The CLI gains `--profile`, defaulting to `fusion-full` for backward compatibility.

Add a `matrix` command that runs all three profiles sequentially for the same suite and repeat count. Sequential execution avoids provider-rate and local-browser contention. Each profile still uses the same runner/executor interfaces.

### Workspace and Evidence Isolation

Every matrix sample receives a stable path containing profile, task, and repetition, for example:

```text
<workspace>/fusion-full/arena-website/run-01/
<workspace>/fusion-minimal/arena-website/run-01/
<workspace>/direct/arena-website/run-01/
```

Transcripts, produced files, stderr/stdout from acceptance commands, and per-sample metrics remain available under that sample path. No repetition overwrites a previous transcript or artifact.

### Reporting

Extend reports with backward-compatible run metadata:

- schema version;
- suite name;
- profile;
- provider/model identity;
- seed and repeat count;
- timestamp;
- declared profile exclusions.

Older reports without metadata must still load. Matrix output writes one report per profile plus a summary containing:

- behavioral pass count and rate;
- mean and distribution-ready sample values for model calls;
- mean elapsed time;
- absolute and percentage deltas versus `direct`;
- failure and rate-limit counts.

No result is labeled “better” solely because it is faster or uses fewer calls; behavioral success is shown alongside cost.

### Errors and Rate Limits

Existing rate-limit classification and retry behavior remain shared. A failed provider call, Direct extraction error, timeout, tool failure, or acceptance failure becomes a failed sample with an explicit reason. Matrix execution continues with the remaining profiles and samples unless the existing global rate-limit policy requires stopping.

## Implementation Boundaries

Expected ownership is:

- `evals/profiles.py`: profile enum, runner factory, and profile metadata;
- `evals/agent_runner.py`: full and minimal agent runners without changing full-profile behavior;
- `evals/direct_runner.py`: single completion and strict artifact extraction;
- `evals/executor.py` and `evals/runner.py`: sample identity and evidence isolation;
- `evals/report.py` and `evals/metrics.py`: backward-compatible metadata and matrix summary;
- `evals/cli.py`: `--profile` and `matrix` user interface;
- focused tests under `tests/test_eval_*.py`.

Exact file placement may be adjusted during planning if existing module boundaries make a smaller change clearer, but the profile contracts and independence invariants are fixed by this design.

## Test Strategy

Unit tests cover:

- profile parsing and the backward-compatible default;
- full-profile dependency parity with the current runner;
- minimal-profile feature exclusions and retained file tools;
- Direct request count and strict extraction success/failure cases;
- event-based call accounting for every profile;
- acceptance-criterion independence from profile prompts and verifiers;
- unique workspaces and retained transcripts across repetitions;
- old report loading and new metadata serialization;
- matrix aggregation and partial failure behavior.

The existing eval tests, full Python suite, Ruff, and `git diff --check` must pass. A real arena matrix is an explicit validation step rather than a unit test because it invokes a live provider and browser-backed acceptance fixture.

## P0 Completion Criteria

P0 benchmark closure is complete only when:

1. all three profiles run from the CLI against the same arena suite;
2. `--repeat 3` retains nine independently auditable samples;
3. the behavioral evaluator remains post-run and hidden from all profile execution;
4. reports identify model/profile and compare success, calls, and elapsed time;
5. targeted eval tests, full `pytest`, Ruff, and diff checks pass;
6. a real three-profile arena matrix completes and its reports are preserved;
7. the observed comparison is reported as evidence, without converting one run into a universal performance claim.

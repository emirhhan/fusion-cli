# Independent Python review: protected context budget

Reviewed product commits `e8b6a14d` and `c2966adb` on 5 November 2026. Verdict: **APPROVE**, no actionable findings.

The change translates the existing soft history allowance using the same task anchor the in-turn compactor preserves. It does not remove startup instructions or grant additional room beyond a learned overflow cap. Known windows retain a separate model-sized reserve and system-size limit. The 8K/16K reserve correction is consistent with the existing base-budget calculation. Explicit impossible-prefix errors propagate through the desktop request boundary and release turn ownership.

Independent verification used the original project's virtualenv with `PYTHONPATH=src`, without dependency installation, provider calls, native actions, or the entire test suite:

- 75 repository tests passed in 9.52 seconds: `tests/test_protected_context_budget.py`, `tests/test_context_budget.py`, `tests/test_turn_compaction.py`, `tests/test_context_invariants.py`, `tests/test_d4_compaction_errors.py`, `tests/test_manual_compact.py`, and `tests/test_active_context_projection.py`.
- Eight additional external tests passed in 0.65 seconds. They cover exact learned-cap rejection versus a one-character margin, oversized system prompts with known 8K/16K/64K windows, image and tool-argument accounting, and a masked tool history fitting while retaining the immutable prefix and threshold.
- Ruff passed for both modified source files and the new repository test module. Scoped mypy passed for both source files. `git diff --check` passed.

The external tests are preserved in the task workspace at `work/reliability-v2/context-python-review-v4/test_boundaries.py`; they are review evidence rather than product source.

This approval concerns the accounting and lifecycle change. Character estimates and static tool reserves remain estimates; live report correctness and overall assistant quality still require separate acceptance tests.

Reviewed SHA-256 values:

- `src/fusion_cli/engines/agent/context_budget.py`: `68c69c4201a7f7b42544969af7248ce007e78bf99b9e837e0812f933ca1852c6`
- `src/fusion_cli/engines/agent/loop.py`: `9b19b66a2f94af555498a8548bb37a53a44b2822bd0f62943043c8b2e19bcc39`
- `tests/test_protected_context_budget.py`: `82a01887409c6766b8b7f5502fd34e419f85c9fa630ce68c83c5270bedd1bec0`

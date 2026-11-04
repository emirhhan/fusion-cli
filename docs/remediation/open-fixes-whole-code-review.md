# Whole-wave code/spec review

**Final bounded verdict at `e62c73aa`: APPROVE.** Both findings below are resolved. No remaining actionable issue was identified in this closeout scope. The initial findings and probes are retained as review history.

Final compatibility delta: reviewed only the three-file `e62c73aa` diff after the `351c1c70` closeout. Explicitly requested remote tools are excluded from exploration candidates before applying the configured cap, retaining the established explicit-tool exception. Recent ToolSearch discoveries take exploration slots; Python's stable sort retains relevance/registration ordering among equal default priorities. ToolSearch itself remains outside the external budget, and the result limit is unchanged. The added mixed explicit/recent-discovery regression asserts both survive a one-slot exploration budget while the default tool is removed. No existing assertions changed. `tests/test_tool_surface.py -m 'not slow'` passed in this reviewer invocation (exit 0); scoped diff whitespace checks passed. No additional finding. This is a source compatibility approval; full pipeline integration remains the parent's separate gate.

## Final closeout

- E11: `90883a34` captures the original journal immediately after executor completion, before recovery overwrites it. Both cancelled and normal failed outcomes call `_RetryEffectSink.permits_retry`, requiring safe observed events, a present snapshot, the exact serialized original prefix, and only fixed local reader calls in the appended portion. The normal-return branch retains its additional zero-counter/empty-use requirement. Durable writes, observed writes and missing prefixes reject retry; a genuine no-tool failure remains retryable. The four actual-dispatch regressions exercise these distinct cases.
- E09: `351c1c70` reads the checkout's literal version using AST before cleanup, independently of imported installed packages. Both the early builder guard and direct `.spec` path use `checkout_version`; manifest generation uses that same checkout value. The stale-import-plus-matching-metadata case now preserves old output/work, and the synthetic manifest test checks source version provenance.
- Deferred desktop/parser scope: reviewed committed `f1043eae`. Focus invalidates the old frame and sets `focus_required` before attempting native focus; failure cannot be repaired by an unrelated screenshot. Successful focus requires matching observed PID, positive window ID, title and bounds. Interactive mouse, scroll, keyboard and type policy compares current identity/title/bounds and PID, rejecting unresolved or substituted windows. Native `windowInfo` supplies a unique matching CG window identity from AX observations. Read the independent Swift review (`open-fixes-swift-review.md`); its typecheck passed, with native runtime limits explicitly retained.
- Task constraints: the specific English coordinated-predicate, Turkish comma and inflection regressions are covered. Schema and dispatch use the same `prohibited_tool` rule. Family restrictions become an explicit `allowed_tool_names` cap on `deps.execution` before child launch; in-process children retain parent execution restrictions, and serialized background-child options intersect that cap. Unbound team/peer delivery tools are blocked when a family cap exists. Automatic platform web checks honor a web prohibition. Root caps remain captured before prompt hooks and retained across internal recovery.
- Cross-owner checks retain the earlier attachment rejection-before-admission, branch requirement marker, bounded private image journal, ToolSearch surface cap and owner-aware panel reconciliation conclusions. The original broad inspection was not restarted.

Validation at `351c1c70`: the focused `test_session_turn_ownership.py`, `test_runtime_metadata_guard.py`, `test_agent_behavior_remediation.py` and `test_tools_desktop_inspect.py` invocation with `-m 'not slow'` exited 0, with every selected test passing. Used the existing project Python with worktree `PYTHONPATH=src` and `MYPYPATH=src`. Scoped source diff whitespace checks passed. These tests use temporary state and mocked native/execution/packaging boundaries. No application build, install, integration, live desktop/UI, secrets or network operation was performed. This verdict covers the source closeout only and makes no all-suite, model-quality or live acceptance claim.

## Initial review history

Reviewed stable committed implementation `32c6baba..3dd0f22d`, the five remediation specifications/reports, prior Python/TypeScript/React findings and their committed follow-ups. Desktop targeting and prohibition-parser follow-ups were actively being edited by their owner; those edits require a later bounded review and are not declared complete here. No production source was edited.

## HIGH

### P1 — normal failed outcomes bypass durable no-effect evidence

File: `src/fusion_cli/appserver/session.py:3608` (durable snapshot replacement at line 3558).

```python
cevap["_retry_safe"] = (
    getattr(outcome, "tool_calls_made", None) == 0 and getattr(outcome, "tool_uses", None) == ()
)
```

An unsuccessful return with zero counters and empty `tool_uses` is classified as `no_tool_effect` without checking `_RetryEffectSink`, the original interrupted journal, or its exact attempt prefix. The earlier failure-handling code first saves `outcome.messages` over that journal, so a subsequent check of the replacement cannot recover omitted durable proposals. The newly strengthened cancellation branch does check the original snapshot, but normal failure returns do not use that contract. This is a remaining acceptance/integration gap in the existing fallback, rather than a newly introduced line-level regression.

Confirmed through actual `AppSession._dispatch` with synthetic temporary state: a mocked executor saves `[Message("user", task), Message("assistant", "", tool_calls=(ToolCall("pending", "write_file", "{}"),))]` to the supplied journal, then returns `ok=False`, `tool_calls_made=0`, `tool_uses=()`, and messages containing only the user task. The first durable receipt is `no_tool_effect`; submitting the same ID with `yeniden_dene=True` runs the executor a second time. Output: `first_code= no_tool_effect executions_after_retry= 2`. No actual write tool was executed. Existing counters and type contracts do not establish that the independent durable snapshot contains no incomplete write, which is precisely why cancellation now checks both.

Fix: capture the original durable snapshot before failure recovery rewrites it; apply one conservative evidence contract to every no-effect receipt path. Require the exact original attempt prefix plus no potentially mutating appended call, together with safe observed events. Missing/replaced/ambiguous evidence must require observation. Add a normal-failure analogue of the durable-incomplete-write cancellation regression; retain genuine no-tool safe retries.

## MEDIUM

### P2 — early packaging guard can compare an installed package against its own metadata

File: `desktop_build/runtime/build_runtime.py:160`; imported version at line 24.

The pre-cleanup guard calls `require_project_metadata_version(__version__)`, where `__version__` comes from ordinary `from fusion_cli import __version__`. If this build environment resolves an older installed Fusion package instead of this checkout's `src`, both that imported version and distribution metadata can be `0.7.18`, although checkout source is `0.8.1`. The early guard passes and deletes the previous output/work. The `.spec` then reads the actual checkout version using `runpy.run_path` and rejects the build, after those deletions. The direct-script test forces `PYTHONPATH=src`, so it does not cover this resolution mismatch.

Confirmed using only temporary package/work sentinels: mock builder's imported version and `metadata.version` to `0.7.18`; replace `_run_pyinstaller` with the spec's source-version guard for `0.8.1`. The source mismatch raises, but output is `old_package_exists= False work_sentinel_exists= False`. No PyInstaller/build process was invoked.

Fix: derive the expected version from the checkout's actual `src/fusion_cli/__init__.py` before cleanup, as the `.spec` already does, and use that value for the manifest. Add the stale-import-plus-matching-metadata case and assert both old sentinels survive.

## Scope and verification limits

- Reviewed session ownership/cancellation and panel HTTP/event reconciliation; attachment count/size admission and bounded reads; root requirement marker, branch/rewind handling and private image journal codec; ToolSearch discovery cap and recent-selection offering; affirmative lesson evidence/retrieval settlement; delivery projection; tool schema/dispatch/inherited child policy; bounded credential worker; metadata guard; local font resources and platform/PWA routing.
- Previous committed fixes for reused call IDs, attachment revalidation/home expansion, branch requirement loss, browser-capture error recovery and late cancellation acknowledgement are present. Their old findings are not repeated here.
- Two small Python probes used temporary data and mocked executor/packaging boundaries under the existing Python environment with worktree `PYTHONPATH=src`. No suite rerun, real user data, UI/desktop action, secret access, network request, packaging, installation or publication occurred.
- No additional actionable issue was established in the other stable areas inspected. This review makes no all-suite, runtime/model-quality or live acceptance claim. Desktop/parser final changes remain explicitly pending bounded review.

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: APPROVE — both initial findings are resolved, and the final desktop/parser follow-up has received the bounded source review described above. No open findings in this review scope.

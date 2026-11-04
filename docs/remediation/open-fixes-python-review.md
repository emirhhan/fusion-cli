# Independent Python review — open fixes

## System Calculator consent and bounded diagnostics — APPROVE

Latest bounded Python/security verdict: **APPROVE at `f94ea25b`**, including the
cross-contract changes in `c654f35f` and `9ab97f5f`. No remaining CRITICAL, HIGH or
MEDIUM finding identified in this reviewed scope. Native API attestation remains
also subject to the separate Swift review; this is not a live result claim.

- **Producer/trust boundary:** native `appInfo` derives the attestation from the
  actual positive process ID, exact Apple Calculator bundle identifier and resolved
  system bundle/executable file URLs. Python accepts only the successful probe's
  literal boolean `True`, exact bundle and positive integer PID. `DesktopTarget`
  defaults the flag to false, named targets cannot supply it, tool arguments do
  not set it, and consent/public payloads do not persist it. Remembered app consent
  cannot manufacture or preserve a later missing native attestation.
- **Exact reset scope:** only background `press` for the attested app's exact
  `AXButton` / `AllClear` identity is exempt from the generic destructive-word
  classification. Reference PID must match both native target and arguments;
  window ID must match arguments. The decoder bounds input/path length and
  validates integer types, nonnegative path indices, SHA-256-format fingerprint
  and the exact four-part identity layout. This is structural admission, not a
  substitute for native validation: actual window/PID lookup and every current
  tree/fingerprint/unique-identity/path-identity check remain mandatory before
  executing an action. Forging a different button's identity cannot pass them.
- **Draft findings resolved:** initial code still treated identifier-only
  `ClearHistory` and unknown/unlabelled controls as ordinary. Synthetic probes
  exposed both. Final code requires per-action approval for ClearHistory,
  malformed/nonbutton/unknown controls and unrecognized unlabelled references.
  Known ordinary numeric/arithmetic IDs remain ordinary and still pass the generic
  destructive-label check. Non-Calculator gates retain their existing behavior.
- **Identifier vocabulary:** CamelCase/acronym and underscore/nonword boundaries
  are normalized only in the identifier-only AXButton fallback. New tests first
  reproduced 12 failed destructive-gate cases for DeleteAccount, Delete_Account,
  SendMessage and PayNow before this normalization. Human title/description
  precedence remains unchanged and has explicit safe-label/risky-identifier tests.
- **Diagnostic/privacy boundary:** rejected actions remain failures with no retry.
  Python forwards only four named exact-boolean guard results and eight named
  exact-integer value-kind counts, each from 0 through 500. Extra fields, raw
  values, private titles, unknown keys, boolean-as-integer counts and out-of-range
  counts are excluded. The native four-check admission conjunction is unchanged;
  the diagnostic result does not override a failed guard.

Independent verification: **204 tests passed** across risk, policy, background,
display-value, focus/inspect and desktop-effect scopes. Earlier diagnostic-only
verification passed 12 tests (overlapping scopes). Scoped Ruff passed, and mypy
passed for four source files. An additional synthetic test drove actual
`resolve_request` and approval policy for **One, Seven, Two, Three, Multiply,
Equals and AllClear** in both AUTO and BYPASS: all retained `REMOTE_INTERACT`,
ALLOW and no extra prompt with remembered app consent. Protected cases exercise
actual per-action prompts and no-remember behavior for spoofed/missing proof,
wrong PID/window, ClearHistory, other apps and malformed/unknown references.

No production edit, live helper/AX/UI action, private-chat scan, shell/model/network
request, secret access, uv/environment creation, application build or installation
was performed by this review. Pure extracted native-policy tests use synthetic
values and do not invoke the desktop helper. No all-suite or physical Calculator
success claim is made; installed 0→391 acceptance remains a separate gate.

## Actual-focused-window semantics addendum — APPROVE

Latest bounded Python verdict: **APPROVE at `afa1e37b`**. No CRITICAL, HIGH or
MEDIUM finding identified in this two-file semantic-focus delta.

App-only activation and foreground polling now explicitly read `AXFocusedWindow`
rather than `front window` ordering, aligning their source with native validation.
The exact named-window selected-object/AXRaise path is preserved. Missing or failed
focused-window reads do not fall back to window-list order: activation fails or
polling expires with the screenshot invalidated and required-refocus still set.
The two-second settle budget, polling interval and strict foreground PID/title
plus native PID/window-ID/title/bounds checks are unchanged.

Failure diagnostics retain only boolean observation/known/PID-match/title-match
state from the last polling observation, together with the existing diagnostic
request scoped to the intended target. They do not disclose another foreground
application's name/title or turn a mismatch into a successful focus result.

Independent verification: **118 tests passed** across focus/inspect, desktop
policy, mouse and destructive-risk scopes. New fixtures distinguish an unfocused
overlay first in window order from the actual focused main window for app-only
and named requests. Separate activation/poll unavailable-attribute cases assert
no front-order fallback, no successful validation and continued stale-frame lock.
A different-PID failure verifies boolean-only output. Scoped Ruff and source
mypy passed. Reviewed final commit against the tested source; no subsequent
source changes were present.

These script/observation fixtures establish API selection and Python state
behavior, not native AppleScript execution or physical application success.
No live UI/helper/AX probe, private-chat scan, model/network/secret access, uv or
environment creation, build or installation was performed. Installed native
focus and physical Calculator 0→391 acceptance remain separate pending gates.

## Identifier-label destructive-gate correction — APPROVE

Latest bounded Python verdict: **APPROVE at `1c938ca0`**. No remaining CRITICAL,
HIGH or MEDIUM finding identified in this two-file risk correction.

The parallel review identified a valid HIGH/P1 producer/consumer gap after the
preceding `e0b61cd2` review: native inspection could expose an identifier-only
button label while `_ref_label` ignored its identity slot. The earlier approval
alone was insufficient for that action-label risk contract. This corrective
verdict includes the aligned consumer.

The identity layout remains role/title/identifier/description. `_ref_label` first
returns the exact prior joined title-plus-description result, preserving its
priority. Only when that human label is empty and the role is `AXButton` does it
use the identifier slot, matching the newly exported button-label contract.
Other roles, human-label behavior, malformed-reference handling and action
validation remain unchanged. The existing risk-word classifier then applies the
same destructive gate to identifier-only Delete, Send and Pay labels.

Independent verification: **45 tests passed on the final commit** in
`test_desktop_risk.py`. The new tests drive actual `resolve_request` and approval
policy in AUTO and BYPASS, seed remembered app consent, press twice and assert
`REMOTE_DESTRUCTIVE`, `can_remember=False` and a fresh prompt each time. They also
cover Turkish destructive identifiers, harmless identifiers, nonbutton scope and
the stronger title/description priority cases with a genuinely risky `Delete`
identifier. The earlier related risk/policy/background/display/effect invocation
passed 113 cases (overlapping scopes, not an aggregate count). Final scoped Ruff
passed; mypy passed for the changed source. No existing risk assertion was removed.

No production edit, real UI/helper action, private chat scan, shell/model/network
request, secret access, environment creation, packaging or installation was
performed. This is source/risk-contract approval; physical 0→391 acceptance is
still a separate gate.

## UI-label and asynchronous-focus addendum — APPROVE

Latest bounded Python verdict: **APPROVE at `e0b61cd2`** (delta from `a2137bba`).
No remaining CRITICAL, HIGH or MEDIUM finding identified in the reviewed Python
source and its immediate diagnostic/payload handoff. Native API behavior is
separately reviewed; no live acceptance result is inferred here.

- **UI label versus filesystem predicate:** the new exception removes a
  mutation-looking word only when it immediately names a button/control followed
  by an explicit press/click predicate. The public `Tümünü Sil düğmesine bas`
  request no longer becomes filesystem deletion work. Independent deletion,
  removal, output-file writing and UI-building predicates remain covered by
  positive mutation tests. Destructive-click risk policy is unchanged and tested
  with delete/send/payment labels; this exception does not grant UI permissions.
- **Initial review issue resolved:** the first candidate still read the front
  window immediately after raising a named window, allowing the old title to be
  rejected before polling. The committed script instead captures the selected
  window object as its activation target. Separate bounded foreground observation
  must then match that target's PID **and title**. The staged named-window test
  supplies a same-PID wrong-title window before the requested window and verifies
  the first observation does not finish focus.
- **Identity and stale-frame controls:** activation exit status alone is not
  success. The old screenshot is invalidated and required-refocus remains set
  before activation; timeout/malformed/mismatching observations keep it set.
  Success still requires positive native window ID and matching PID, title and
  bounds. Poll subprocess timeouts use the remaining two-second settling budget.
  The existing native-helper phase remains separate from that polling budget.
- **Diagnostics/public metadata:** failure diagnostics request only the intended
  target PID and expected title/bounds; output contains comparison booleans,
  counts and bounded role/subrole metadata rather than raw window titles/values.
  These observations never satisfy a failed identity check. Updated tool wording
  treats absent main/focused/subrole hints as unknown, preserving the distinction
  between a same-process auxiliary window and the selected target. Button label
  and window metadata serialization/native privacy gates are also covered by the
  separately owned native review.

Independent verification: the final focus/display/effect invocation passed
**48 tests**, including the named-window staged case. Earlier bounded interaction
invocations passed 187 effect/policy/agent cases and 71 desktop cases; these are
overlapping scopes, not an aggregate count. Mypy passed for the three changed
Python source files. Final commit Ruff checks passed for changed Python source
and tests after the worker corrected one line-length issue. Test fixture edits
accommodate the timeout keyword and add assertions; existing denial assertions
remain in force, with timeout diagnostics now explicitly tested as read-only
requests to the intended PID.

No production source was edited by this reviewer. Tests use synthetic observations,
fake clocks/adapters and pure extracted native-policy helpers; no actual UI,
native desktop probe, private chat scan, network/model/secret access, build,
virtual-environment creation or installation was performed. Physical Calculator
clear-to-0 followed by an observed 17×23 result of 391 remains a separate live
acceptance gate after installation.

## Corrective browser bootstrap/security re-review — APPROVE

Latest bounded Python verdict: **APPROVE at `be28b603`**. No remaining CRITICAL,
HIGH or MEDIUM finding identified in this corrective delta.

**Correction to the earlier review:** the approval of `6954a28a` missed the fact
that MCP server configuration also supplies secret environment-name exclusions.
Its configuration-replacement approach was unsafe and is superseded; the earlier
configuration-capture tests did not exercise that security consumer. The parallel
review's HIGH/P1 finding was valid. The parent states that candidate was never
installed. The prior approval below is historical, not an approval to use it.

`be28b603` preserves the full original Config and introduces the keyword-only
`bootstrap_mcp` flag, defaulting to true at both `run_agent_task` and
`_run_agent_with_mcp`. AppSession forwards false only for the already checked
built-in browser surface. The flag gates connector bootstrap, its failure notices
and MCP reference expansion; it does not remove configured servers or their
credential metadata. Existing callers retain startup by default, while normal
main turns and unknown/external browser surfaces explicitly retain it. The
hosted-connector branch remains independent of the MCP skip flag.

The security regression now goes through actual AppSession → run_agent_task →
_run_agent_with_mcp plumbing and actual `apply_runtime_settings` / `_shell_env`.
Only the final model runner, connector starter/reference expander and source
environment are faked. It checks multiple configured `env_names` and `token_env`
names are absent from all three resulting child environments, `hidden_env`
retains those names and a public marker survives. It also checks original Config
identity, shell/native-alias availability and actual mocked bootstrap counts:
zero after local browser, one after main, two after external fallback. This
directly covers the security consumer missed by the earlier review; no shell is
launched and no values are printed.

Independent verification: **63 tests passed** across browser startup,
ownership/submission, environment scrub, runtime context and CLI session scopes.
Ruff passed for both changed source files and the regression file; mypy passed
for both source files. No production source was edited, and no real secret,
shell/connector/model/network/UI action, build or installation was used.

## Browser MCP startup addendum — historical approval, superseded above

Bounded review of **`6954a28a`** completed; no CRITICAL, HIGH or MEDIUM finding
identified. This is the latest reviewed Python delta following the post-live
approvals below.

The actual runner calls `ensure_mcp_tools` from `config.mcp_servers` before its
allowed-tool surface takes effect. This change supplies an empty server tuple
only in a per-runner configuration for a browser-only turn whose complete merged
allowlist is contained in the built-in registry plus local `ask_teacher`.
Chrome's MCP-shaped aliases are registered built-ins. Pending skill restrictions
intersect this surface. Unknown/external allowed names preserve configured MCP
startup, and the native path does not enter the bypass. The replacement neither
mutates the session configuration nor changes persisted settings, and hosted
connectors are outside this change.

The code/chat regressions assert the actual captured runner configuration and
native alias set, then execute another normal turn and verify its connector
configuration remains intact. A future external-name fixture verifies conservative
fallback. The built-in registry check constructs tool definitions without starting
connectors. No live performance claim is inferred from these tests.

Independent verification: **39 tests passed** across browser-MCP startup,
session ownership and submission scopes. Scoped Ruff and mypy passed. Tests use
temporary profiles, synthetic connector settings and mocked agent execution;
no connector command, UI action, network/model call, secret access, build or
installation was performed. No production source was edited by this review.

## Final post-live source addendum — APPROVE

Bounded review of **`449813bf`** completed. No CRITICAL, HIGH or MEDIUM finding
identified in this delta. This extends the preceding approvals for `30ced7fe`
and `d8c5f6b5` to the requested effect/focus/display follow-up.

- **Effect classification:** file-mutation object/verb matching now operates on
  positive clauses instead of borrowing a noun across sentences or completed
  predicates. Coordinated build objects retain their shared verb; filename dots
  remain intact. The tests retain real application/HTML/source-file mutation and
  external-effect gates alongside Calculator sentence/comma/newline cases and
  explicit prohibitions. The desktop-lane inflection change is limited to the
  additional Turkish application-object form; web/mobile negatives are tested.
- **Admission boundary:** the scripted Calculator regression uses the real agent
  schema, permission and semantic-admission paths with a synthetic trusted target.
  It asserts both delivered click/key operations, the desktop lane, the noncomplex
  workspace classification and the offered desktop schemas. This is meaningful
  coverage that a classification fix does not silently prohibit requested GUI
  interactions. It does not claim the application reached a result.
- **Focus/public identity:** text and `structured.target` expose the same already
  cross-validated window ID/PID. A regression passes that exact structured pair
  to background inspection and asserts the native operation/arguments. Existing
  failed-focus and target-consistency checks remain covered. Descriptions correctly
  identify the name-only legacy window list as unsuitable for obtaining IDs.
- **Display privacy/serialization:** Python preserves the native literal display
  value without calculation or replacement. Native serialization adds only the
  gated noneditable static-text value, source label and truncation flag; exported
  values are capped at 1,000 characters. The pure helper test exercises secure,
  input, unknown and editable denials, ancestor propagation, nil values and the
  length cap using extracted production helper functions. Detailed native API
  behavior/typechecking is also under the separate Swift review; this Python
  verdict does not claim live accessibility acceptance.
- **Tests/fixtures:** reviewed changed fixtures and assertions; the added empty
  `turn_forbidden_families` field supplies the existing default contract rather
  than bypassing a restriction or weakening an expected denial.

Independent verification: **219 tests passed** across desktop effect planning,
display value, inspect/background, expertise, effect detect/admission/policy,
tool contract and agent behavior regression scopes. Ruff passed for changed
Python source/tests; mypy passed for all five changed Python source files.
The display test executes only pure extracted Swift helpers with synthetic
strings; all OS/model/provider interactions are mocked. No real UI action,
screen/accessibility probe, model/network request, secret access, build or
installation was performed.

## Post-live bounded addendum — APPROVE

Reviewed only **`30ced7fe`** and **`d8c5f6b5`** for the requested keyboard and
vision-helper boundaries. No CRITICAL, HIGH or MEDIUM finding identified in these
two deltas. This addendum does not approve the separate effect/focus/AX work still
in progress.

- **Arithmetic key events:** the new keypad mapping applies only when the parsed
  chord has no Command, Control, Option or Shift flag. Explicit modifiers continue
  through the existing physical keycode/flag path, including shortcuts parsed from
  key syntax or legacy boolean fields. `_post_key` still sends down/up pairs with
  the same flags and resource release behavior; repeat and hold are unchanged.
  Named navigation and Windows dispatch do not enter the new mapping. The fake
  CoreGraphics tests exercise the actual event-construction boundary, including
  Turkish ANSI-equals substitution, modifier flags, release order and hold/repeat.
  They establish event selection, not native keyboard-layout or application-result
  correctness. The remediation report states that limit accurately.
- **Vision helper contract:** fixed literal-observation instructions are in a
  system message above the original user question/image on both attempts. Every
  successful description gets an explicit model-observation/non-independent-
  verification label. Output is still a description string rather than a parsed
  or validated visual result. The existing first 200-token attempt, one 4096-token
  truncation recovery, shared 60-second completion deadline, zero provider retries,
  nontruncation error behavior and cancellation propagation remain intact.
- **Evidence limits:** the vision document explicitly records that baseline and
  grounded synthetic fixtures both produced correct semantic transcriptions and
  that the original false positive was not reproduced or proven fixed. The new
  prompt and provenance label are not a hard task-success verification gate.

Verification performed here: **132 tests passed** across
`test_desktop_literal_keys`, `test_tools_desktop`, `test_key_spec`,
`test_desktop_win32`, `test_image_view_budget` and `test_view_image`; Ruff passed
for changed Python source/tests; mypy passed for the two source files. All tests
used synthetic data/adapters. No real keyboard/UI event, screenshot inspection,
provider/model call, credential access, build or installation was performed.

## Final bounded re-review — APPROVE

Final reviewed snapshot: **`e62c73aa`**, including fixes `bfc2ddda`, `3dd0f22d`,
`f1043eae`, `90883a34`, and `351c1c70`. All seven original actionables below are resolved.
No remaining CRITICAL, HIGH or MEDIUM finding was identified in the requested
bounded re-review. The earlier BLOCK decision below is retained as review history.

| Original actionable | Resolution verified |
| --- | --- |
| E11 reused IDs conceal a new durable write | A frozen serialized history-plus-user prefix establishes the attempt boundary; only appended calls qualify as new evidence. Reused/identical IDs cannot hide writes; absent or changed prefixes require observation. |
| Failed focus leaves stale coordinates | Focus invalidates the old frame immediately and sets required-refocus state. Neither a failed/malformed observation nor another screenshot re-enables input. Valid focus and a new frame are required. |
| Another window in the same PID passes | Focus binds a verified CG window ID, title and geometry. Point and foreground keyboard/type/scroll policy checks current window identity, bounds and PID; unresolved/substituted/moved windows are blocked. |
| Attachment revalidation silently drops images | Revalidation raises a bounded explicit error. Direct and receipt routes reject the race before agent execution or receipt ownership. |
| Mixed predicates corrupt prohibition scope | The reproduced English positive predicate, Turkish trailing comma instruction, coordinated object bans and inflected computer-control prohibition have regressions. Schema/dispatch restrictions also persist through child tool caps; unbound team/peer routes are blocked under a prohibition. |
| Branch loses recovered root requirement | A dedicated typed metadata event preserves the bounded requirement through reload, repeated branch and rewind without copying general harness notes or counting it as a user turn. |
| Home expansion RuntimeError escapes | Expansion is within bounded validation; the synthetic unavailable-home error becomes an explicit rejection without raw detail. |

Additional requested follow-up from the parallel review was also checked:

- **E07 explicit-tool compatibility (`e62c73aa`, three-file delta):** explicitly
  requested remotes are excluded from exploration-budget candidates before
  trimming, preserving their existing allowlist exception. Recent discovered
  nonexplicit tools still take the configured exploration slots, and stable
  sorting preserves relevance/registration order for the remaining defaults.
  The new cap-one regression checks that an explicit remote and a newly loaded
  remote both remain offered with ToolSearch. Existing assertions were unchanged.
  Bounded re-review found no new issue. Tool-surface, context-regression and MCP
  ToolSearch suites passed (73 tests); scoped Ruff and mypy passed.
- **E11 ordinary failed outcomes (`90883a34`):** the original journal entry is
  captured immediately after execution, before recovery/history replacement. A
  shared `permits_retry` contract requires both observed safety and exact durable
  attempt evidence for cancellation and ordinary failure. New tests cover a
  durable write omitted from returned messages, an observed write with zero
  returned counters, missing prefix and safe no-tool retry. Unsafe cases retain
  `executor_failed` and do not execute a second attempt.
- **E09 checkout/import mismatch (`351c1c70`):** the build guard reads the actual
  checkout version as an AST string constant before destructive cleanup, compares
  installed metadata to it and uses that same value in the manifest. Direct spec
  invocation uses the shared checkout reader. Stale imported-version state cannot
  authorize replacement or contaminate the manifest. Tests use a mocked packager
  and temporary output only.

Re-review verification (all exited 0):

- Ownership, context and image attachment regression suites.
- Transcript store/persistence and submission interaction suites.
- Focused agent behavior, desktop inspect/mouse/policy suites, including failed
  focus, same-PID other-window, changed geometry/title and missing identity cases.
- Final E11 ownership/submission and E09 metadata-guard suites: **41 tests passed**.
- Ruff passed on reviewed Python source/test scopes. Mypy passed on session,
  attachment and transcript source (3 files), desktop/agent source (6 files), and
  final session/build guard source (3 files).
- An additional synthetic integration check confirmed image-race rejection on
  **both** direct and receipt routes before model execution or receipt claim.

No implementation edits, broad new bug hunt, live desktop/helper execution,
network/model/credential action, build, installation or publication was performed.
Native Swift typechecking and its independent review are recorded by the desktop
owner/parent, not claimed as execution by this Python reviewer. Approval covers
the bounded source findings; packaged/live acceptance and the documented bounded
natural-language grammar limits remain separate.

## Initial review — historical findings, now resolved

Reviewed snapshot: `32c6baba..3a4669fa` (commits c614b1b6, 1c6790b0,
2e0cd513, 53bbc64d, 496316da, 3a4669fa). Line references below are for that
snapshot. Read the five requested remediation plans/reports and reviewed changed
Python source and tests. No implementation edits were made.

**Initial decision: BLOCK (superseded above).** Six HIGH findings and one MEDIUM finding were identified. The
reproductions below use temporary local data and mocked execution/OS adapters;
no real tool effects, desktop events, network requests, credentials or model calls.

## Findings

[HIGH / P1] Reused tool-call IDs hide durable incomplete writes from retry classification

File: `src/fusion_cli/appserver/session.py:3472`

Issue: The durable cancellation check excludes every call whose ID occurs in prior
history, without comparing the call or its position. Tool IDs are provider/model
input and this path does not establish uniqueness across the history. A new
incomplete mutating call with an old ID therefore disappears from the evidence.
Synthetic reproduction through the actual `_dispatch` and `_cancel_turn` paths:
seed prior history with completed `read_file(id="reused")`; mocked executor saves
that history plus new `write_file(id="reused")` in the journal, emits no start
event, and waits; cancel. Receipt error code is **`no_tool_effect`**, authorizing
retry despite a durable incomplete write. This violates E11's conservative retry
contract.

Fix: Identify the attempt's appended messages/calls using an established durable
boundary, or verify an exact unchanged history prefix. Reused IDs, mismatching
prefixes and ambiguous snapshots must require observation. Add the above
regression and retain the safe no-tool/reader cases.

[HIGH / P1] Failed focus removes the binding while leaving stale coordinates executable

File: `src/fusion_cli/tools/desktop_inspect.py:156`

Issue: Focus clears `focused_window` immediately but clears `frame` only on success
at line 184. A failed AppleScript operation or malformed observed identity can
have changed foreground state, yet the old frame remains usable and the prior
target restriction disappears. Synthetic check: seed a frame and bound PID 42,
mock `_run` to return a focus failure, call `desktop_window_focus`; `frame` is
still present, `focused_window` is `None`, and `_to_point(context, (100, 100))`
returns a usable point. Policy no longer applies its focused-PID guard.

Fix: Invalidate the old frame before attempting focus, and retain an explicit
unverified/required-refocus state after any failed identity check. Test native
failure and malformed successful output through policy and dispatch, asserting
that no mouse event is delivered until valid focus and a fresh screenshot.

[HIGH / P1] Focus verification binds only the process, allowing another window in it

File: `src/fusion_cli/tools/desktop_policy.py:346`

Issue: The stored tuple omits window identity (`desktop_inspect.py:183`), and the
point policy compares only PID. The stale stored rectangle is checked by the mouse
adapter, but neither current window identity nor current geometry is checked. A
second window/dialog in the same process overlapping that rectangle passes.
Synthetic probe returning PID 42 for a different window produces
`DesktopAssessment.blocked is None` for an in-rectangle point. The actual Swift
point probe currently supplies process/element information, not a verified window
binding, so Python cannot establish the promised window consistency.

Fix: Bind a stable observed window identity and geometry; resolve the point's
actual containing window and compare both identity and current bounds before
event delivery. Unresolved, moved or substituted windows must require renewed
focus/screenshot. Include same-PID/different-window and moved-window regressions.

[HIGH / P1] Attachment revalidation silently drops an admitted image after a file race

File: `src/fusion_cli/appserver/attachments.py:64`

Issue: Both session routes first call `attachment_context`, then load images in a
worker. `attachment_images` revalidates, but returns `()` on a newly detected
error. Its comment assumes admission already reported that error, which is false
if the image was deleted, grew over the limit or became unreadable between those
two validations. Reproduction: create an image path, confirm first validation
returns no error, remove it, then call `attachment_images`: returns `()` rather
than raising. Session consequently starts with the old metadata and no image.

Fix: Raise a bounded validation error on this second check so the session's
existing `ValueError` handlers reject visibly before claim/execution. Test the
race through both receipt and direct submission routes, asserting no model call
and no durable receipt ownership for rejected input.

[HIGH / P1] Prohibition parser loses direct Turkish bans and extends English bans into positive instructions

File: `src/fusion_cli/engines/agent/tool_constraints.py:23`

Issue: One clause is treated as one prohibition scope. Because commas are not
clause boundaries and the Turkish matcher requires the ban at the very end,
`Terminal kullanma, sadece görseli oku.` returns an empty set. Conversely,
`Do not use terminal and use browser.` returns both SHELL and BROWSER, denying
the positively requested browser. These are direct imperatives within the stated
bounded grammar, rather than requests for general language understanding. The
missing ban reaches both schema offering and execution because both rely on this
same parser.

Fix: Parse coordinated noun lists separately from coordinated predicates and
attach negation to its predicate/object scope. Cover both examples while keeping
`terminal, browser veya desktop kullanma` coordinated bans and quoted/code
examples correct. Also consider direct Turkish inflection:
`Bilgisayar kontrolünü kullanma.` currently returns an empty set.

[HIGH / P2] Branching a bounded reloaded conversation discards its recovered root requirement

File: `src/fusion_cli/cli/repl/transcript_store.py:112`

Issue: Root recovery is represented exclusively as `harness_note=True`. The
existing `conversation_prefix` filter at line 377 drops every harness note, so
`copy_conversation` removes the only retained root requirement. Verification
passes against that already-filtered prefix. Synthetic reproduction with 102
messages: load the source and observe `ROOT_REQUIREMENT` in the recovery note;
copy those loaded messages to a new conversation; reload the branch and the root
is absent. E05 works for reload alone but regresses immediately on branching.

Fix: Preserve root-requirement provenance through branch/fork explicitly, while
continuing to exclude ordinary harness instructions and keeping the 100-message /
8,000-character bounds. Test reload → branch → reload and repeated branching,
checking one retained root requirement and no repeated recovery notes.

[MEDIUM / P2] Invalid home expansion escapes attachment validation as RuntimeError

File: `src/fusion_cli/appserver/attachments.py:30`

Issue: `Path(path).expanduser()` runs outside the exception handler. A syntactically
valid request containing `~definitely_missing_fusion_user/x.png` raises
`RuntimeError` instead of returning the explicit attachment rejection required
by E03. This occurs before any file access or model execution.

Fix: Include path construction/expansion in bounded validation and catch the
relevant `RuntimeError`/`ValueError` cases. Test malformed and nonexistent-user
home paths through both submission routes without exposing raw exceptions.

## Verification and limits

- `git diff -- '*.py'` was clean at review start; reviewed the explicit commit
  range instead of relying on the worktree diff.
- 68 targeted tests passed: `test_session_turn_ownership`,
  `test_context_data_regressions`, `test_agent_behavior_remediation`,
  `test_web_credential_wait`, `test_runtime_metadata_guard`, `test_desktop_mouse`,
  and `test_tools_desktop_inspect`, with `-m 'not slow'`.
- Ruff passed for the changed source scopes (including agent modules).
- Mypy passed for 11 scoped source files: attachments, image input, tool
  constraints, credential worker, journal/codec, desktop inspect/mouse/policy,
  ToolSearch and metadata guard.
- Runtime: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python`,
  with worktree `PYTHONPATH`/`MYPYPATH` set to `src`.
- The synthetic probes described above completed and reproduced each finding.
  Passing existing tests do not exercise these cases.
- No additional P1/P2 finding identified in E09 metadata guard or E10 credential
  worker. No all-suite, packaging, installation or live desktop acceptance run.
- Bounded re-review should cover these fixes and their new regressions; original
  model-quality and live acceptance limits remain as documented by the owners.

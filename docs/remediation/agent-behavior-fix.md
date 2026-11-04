# Agent behavior remediation

Scope: E02, E12, E15 and the observed Calculator coordinate failure. Changes are confined to the isolated `fusion-deep-fixes` worktree. No live desktop, model, browser or user-file operation was used for verification.

## E02: learned success and retrieval feedback

The old evidence gate accepted every tool message, including a failed call. The independent success-criterion gate only ran with `lesson_attributed_feedback` enabled. With that flag disabled, a clean turn also rewarded every retrieved lesson without evidence that it was used.

Learned SUCCESS now requires a successful observation and applicable passed verification criteria, regardless of the attribution flag. A failed or unknown-status tool result cannot support a success lesson. A failed tool can still teach a MISTAKE from its observed failure. Retrieved lessons use the existing operational-use/criterion proof contract in both flag states; a successful final answer alone does not change their confidence. Explicit manual/seed knowledge storage is unchanged. This change does not infer verified knowledge from ordinary chat.

## E12: irrelevant delivery evidence

A successful informational shell command such as `date` populated `command_runs`, which was sufficient to create a delivery payload with no files, criteria, problems or verification. The UI consequently rendered an unexplained “Teslim doğrulanmadı” card.

Only behavioral verification commands, changes, criteria, job deliveries, tamper findings or meaningful gate/blocker notes now trigger the delivery projection. Warning-only and failed gates remain visible. No UI change is needed.

## E15: original request constraints and automatic recovery

A small explicit prohibition contract maps direct Turkish/English tool-family prohibitions to the existing schema and dispatch boundary. Coordinated nouns share one prohibition scope; quoted examples and code are excluded; clauses separated by punctuation or contrast words have independent scope. Both ASCII and Turkish spelling are supported. Coordinated predicates have separate scope (`Do not use terminal and use browser` denies only shell); a Turkish negative verb closes its object list before a comma (`Terminal kullanma, sadece görseli oku`). The direct `kontrolünü` noun inflection is supported. This is intentionally a bounded imperative grammar, not a general natural-language permission classifier. Ambiguous instructions outside that grammar still require model instruction following.

The original root request is the authority: `AgentDeps.turn_forbidden_families` is captured before prompt hooks; every execution policy intersects this cap. Schemas and dispatch reject forbidden families, including shell aliases. Replans and internal correction tasks cannot erase the original cap. The filtered tool set is also materialized in the existing `allowed_tool_names` cap so in-process children and background `TaskOptions` inherit the same restriction. Team workers and messages to pre-existing peers do not preserve this turn's envelope, so `team_run`, `SendMessage` and `send_message` are conservatively unavailable while a family prohibition applies. Deterministic shortcut workflows defer to normal guarded execution when that cap is present.

Automatic teacher planning/recovery requires an affirmative operational change effect. A failed image observation in an informational task no longer forces a teacher plan or takeover. Explicit model-requested teacher advice remains available, and existing verifier behavior still avoids repair loops for nonmutating informational turns. This does not guarantee a model never chooses a redundant image question; that remaining quality behavior needs an offline scripted/live acceptance evaluation with the selected model.

## Grounded desktop coordinates

`desktop_window_focus` previously returned success when AppleScript merely exited successfully. It now reads and validates the observed foreground application, process ID, window name and geometry. It invalidates the previous frame and requires a new screenshot. Accessibility output supplies element geometry when available without dropping elements that lack bounds.

Subsequent point actions must lie within that observed target window. The native probe resolves its actual containing AX window to one unambiguous CGWindowID, title and geometry. Focus stores that identity after cross-checking the foreground observation. Point actions, scrolling, typing and keyboard actions must still match that process, window ID, current title and geometry; missing, moved or substituted windows are blocked before dispatch. A failed or malformed focus invalidates the previous screenshot and leaves a required-refocus state: taking another screenshot alone cannot remove it. Existing risk and application permission gates remain intact. Moving/switching the target can require a fresh focus and screenshot; the binding is conservative rather than silently accepting another app.

A click is reported as an event delivery, not proof that Calculator was cleared or that multiplication succeeded. Application state must be inspected afterward. Live acceptance must confirm clear-to-zero and the actual 391 result for 17×23; that operation was deliberately not executed by this worker.

## Verification

Regression tests were first observed failing for failed-tool evidence, default retrieval rewards, unverified learned success, irrelevant `date` delivery, unverified focus and out-of-window coordinates. Offline targeted tests cover those cases, warning/blocker preservation, inherited policy caps, schema filtering, shell aliases, successful-observation lesson storage and unknown/different desktop process IDs.

The first broad lesson run included slow Chroma storage tests and waited in the optional storage/embedding path; it was interrupted. Subsequent worker runs exclude `slow` and use only scripted providers and temporary data. The parent integration run records the final aggregate test and review results.

## Python review follow-up

The initial review reproduced four missing cases: stale screenshot reuse after failed focus, another window in the same process, an English positive predicate absorbing a preceding prohibition, and a Turkish ban lost before a comma. Those cases were first reproduced as failing synthetic tests. Follow-up regressions also cover current geometry/title changes, missing window identity, keyboard/typing drift, required refocus after a fresh screenshot, background child cap serialization and unbound peer/team dispatch. `/usr/bin/swiftc -typecheck src/fusion_cli/tools/data/desktop_host.swift` succeeds without executing the helper or reading the desktop.

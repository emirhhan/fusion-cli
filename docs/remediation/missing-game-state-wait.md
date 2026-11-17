# Missing game-state hook and final-verifier latency

The post-teacher-policy counter turn produced a final model answer at 84.044
seconds but reached its 180-second deadline without a later public event. The
model had called `play_probe` on the counter. Its trace did not retain that
tool's target, so the exact prior context cannot be reconstructed as fact.

A separate diagnostic used immutable `51b79738` code, the identical counter
artifact, and actual composite verifier implementations. It compared two
explicitly reconstructed contexts: no recorded game probe, and an owned HTTP
preview recorded in `probed_games`. The latter also makes `GameProbeVerifier`
test the file URI. Every verifier and game probe was delegated unchanged;
only stage timing and asynchronous stack locations were recorded.

The control completed in 1.279 seconds. In the seeded context, the file probe
took 55.033 seconds and the HTTP probe took 55.280 seconds. The seeded composite
completed in 110.834 seconds, including 110.314 seconds in `GameProbeVerifier`.
Stack snapshots at 15, 30, and 45 seconds ended in
`game_hud.restart_after_end` waiting for another poll. The counter has no
`__GAME_STATE__` hook. Visual verification was disabled and its verifier was
not constructed. These observations isolate the wasted end-state wait; the
reconstructed experiment is not a replay proving the omitted original target.

`restart_after_end` documented that a missing hook was unmeasurable, but treated
`None` as an ongoing game and polled for the full 45-second budget. The fix
returns the existing unmeasured result immediately when the state hook is
missing or disappears during polling. Actual playing states retain the same
45-second limit. Existing end-state restart/HUD checks, probe evidence, result
wording, and game-verifier selection remain unchanged.

Two new cases failed before implementation: an initially missing hook and a
hook disappearing after one poll. Separate checks preserve the playing-state
wait budget and the existing unmeasured summary. Existing browser-backed
restart tests remain part of the verification gate.

The diagnostic also exposed false game findings on the counter: a static
counter was rejected for having no moving enemies. Reducing the wait alone
would leave that defect and could prompt an unrelated game modification.
After a completed short probe, `run_play_probe` now omits game registration
only when the task does not request a game and every observed game-state and
canvas field is absent. Its output is an explicit `not_applicable` observation,
not a claim that game acceptance passed. Game requests, observed state hooks,
and actual canvas observations preserve the existing registration path,
including broken or motionless canvas games.

Two more cases failed before this registration fix: the policy-level counter
observation and a real Chromium counter probe. The latter now runs through the
ordinary full composite closure without game findings. The change does not
attempt to classify every possible canvas page or redesign tool profiles.

The combined game/probe regression gate passed 64 tests in 71.72 seconds,
including the real Chromium counter-to-composite case and the existing actual
game restart/HUD tests. Ruff check/format on both changed modules and both new
test files passed; mypy on both changed modules passed. Source-scoped independent
reviews and a new full model turn remain separate acceptance gates.

Python review then found that the initial `not_applicable` branch also omitted
real page console errors. The correction keeps generic console, browser rAF,
and resource observations in text and bounded structured metadata. Console
errors or low measured rAF produce a failed observation even though game
acceptance remains inapplicable; the target is still not registered as a game.
Only game-specific enemy, start, and restart findings are omitted. Controls
cover ReferenceError, failed resources, low rAF, benign favicon notes, loaded
images, and a real Chromium page with a JavaScript ReferenceError.

After that correction, all 70 game/probe tests passed in 80.74 seconds. Ruff
check/format on the changed module and test file and mypy on `web_tools.py`
passed. The independent reviewers must assess this final correction rather
than treating the earlier 64-test gate as approval of the revised branch.

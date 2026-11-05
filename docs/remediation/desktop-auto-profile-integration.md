# Desktop execution profiles

The shared `/mode auto` command enabled `ReplState.auto_profile`, but desktop
`AppSession._run_turn` never consumed that flag. CLI/TUI selected a profile before
every agent turn; desktop kept its previous model and candidate configuration.

The desktop now uses the same classifier, profile alias resolution and `apply_tier`
logic as CLI/TUI through `config.profile.auto_turn_config`. It selects after the
owned turn task exists, with classification/import work in `asyncio.to_thread`.
The selected configuration reaches the existing `run_agent_task` path, preserving
its tools, persona, approvals, evidence and provider capability checks. No alternate
engine or provider call path is introduced.

The submission captures both the configuration and auto flag at acceptance.
Completed-submission replay does not select or execute again. Automatic continuation
reuses the selected configuration instead of classifying synthetic continuation
text. Missing tiers preserve the existing model. Auto disabled leaves manual and
strict model choices unchanged. Explicit skill model/effort overrides remain above
profile selection. Disabled MCP connectors remain excluded from the turn without
removing them from the session catalogue.

Profile reasons use the normal correlated `StatusChanged` event. The current
session adopts the selected profile only while the captured state, configuration
and visible conversation generation still match. Cancelled classification workers
only compute a value; they cannot mutate session state or start an executor.

This execution profile is separate from the composer's automatic permission mode
and the web provider's `/auto` model identifier. It requires `/mode auto`; neither
of those other settings enables execution-profile selection.

## Verification

`tests/test_appserver_auto_profile.py` exercises real AppSession command/submission
routing with only the executor/provider boundary replaced by a local fake:

- shared profile selection, executor configuration and correlated explanation;
- replay exactly once, strict/manual preservation, and unavailable tiers;
- accepted configuration/flag snapshots;
- nonblocking classification, busy rejection and cancellation;
- independent live session progress and visible-chat generation changes;
- automatic continuation, skill precedence and disabled MCP connectors.

The original failure was observed before implementation: desktop never invoked the
classifier. The connector-filter interaction was also observed red before its fix.
Targeted shared profile, command, session, submission, model-picker and selection
ownership suites are run with the original project virtual environment and
`PYTHONPATH=src MYPYPATH=src`; scoped Ruff, mypy and diff checks are run separately.
No full-suite, real provider/network, native application or signed-runtime test is
claimed. Packaging and live installation are separate release checks.

Recorded results on 2026-11-05:

- Nine-file targeted batch: **209 passed**, one existing Pydantic `ReadOnly`
  schema warning in
  `test_masaustunde_shell_reddi_ucuncu_model_cagrisi_yapmadan_turu_durdurur`.
- Final dedicated AppSession file, including the additional visible-generation
  guard case: **10 passed** (210 distinct tests across these runs).
- Ruff check and format check: passed on all four touched Python files.
- Mypy with `--follow-imports=silent`: no issues in the three touched source files.
- `git diff --check`: passed.

## Follow-up: receipt-bound profile adoption

Independent review reproduced a pre-start race: a job could pause while persisting
its `running` receipt, `oturum.baslat` could bind a different chat using the same
ReplState/config, and the resumed job would capture that new chat's generation.
The original guard then incorrectly adopted the old job's low profile into the
new chat. Checking only the generation captured when classification starts misses
this earlier window.

Profile adoption now carries the visible generation captured with the receipt key,
before admission lookup/claim or running-state persistence can yield. Configuration
and auto-flag snapshots still determine the accepted job's actual executor config.
The generation only controls whether that job may publish its selected profile
back into the current session configuration; it does not alter execution routing.
A monotonic generation also rejects old→new→old chat switches that restore the
same conversation id, ReplState and config identity.

Eight actual AppSession admission tests pause either after durable claim or before
persisting `running`, then use `oturum.baslat` to switch chat, switch away and back,
or change project root. No-rebind controls still adopt the selected profile; all
variants preserve the expected accepted executor configuration and receipt chat id.
The running-state variants also check rejection of a second submitted job.

Observed red before the fix: conversation and round-trip running-state variants
failed. Capturing only after claim additionally left three claim-window variants
red; capturing beside receipt-key creation makes all eight green. The final
AppSession auto-profile file passes **18 tests**; existing cancellation, snapshot,
manual/strict, skill, connector and continuation cases remain included.

Follow-up verification on the final receipt-bound source: **186 passed**, one
existing Pydantic `ReadOnly` warning, across `test_appserver_auto_profile.py`,
`test_appserver_submission.py`, `test_appserver_session.py`,
`test_appserver_commands.py`, `test_appserver_model_picker.py` and
`test_model_selection_ownership.py`. Ruff check/format, scoped session mypy and
`git diff --check` pass. No real providers, native applications, full suite,
packaging or installation were exercised.

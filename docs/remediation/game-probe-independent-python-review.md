# Game-probe scope and missing-hook wait: independent Python/general review

Reviewed commits: `74e095e7` and diagnostic-preservation correction `d7ebfad2`, 2026-11-05.

**APPROVE the scoped changes.** No HIGH or CRITICAL issue remains in the reviewed game-HUD wait and probe-registration branches.

An absent or disappearing game-state hook now returns the existing unmeasured result without spending the whole 45-second end-state wait. A real continuing playing state still receives that same 45-second budget, and existing ended-game restart/HUD behavior remains covered.

The inapplicable-game branch is conservative: the task must lack game context and all observed game-state and canvas fields must be absent. Actual game contexts, any observed state, every canvas kind and legacy canvas-change evidence retain registration for final game verification. An inapplicable game probe does not register a game gate or claim game acceptance. Non-game canvas pages remain outside this narrowly corrected absence-of-game-evidence case; the change is not a universal page classifier.

The first candidate silently dropped genuine non-game console failures together with game-only visual findings. An independent reproducer showed a counter `ReferenceError` returning a clean inapplicable observation. The correction now retains bounded general page diagnostics, resource notes and loaded-resource observations. Actual console errors or low measured main-thread rAF return a visible failed page observation; benign favicon notes remain nonfatal. Game-only enemy/start/restart findings are omitted only in the inapplicable branch. No game budgets, verification profiles or permission boundaries were changed.

Independent verification:

- Fresh final-source `ReferenceError` reproducer: error visible, `ok=False`, explicit game `not_applicable`, no game-gate registration.
- Ruff and mypy passed on both modified source modules.
- **58 tests passed in 26.03 seconds**, covering missing/disappearing hooks, preserved playing wait, game/state/canvas registration, general diagnostics, actual Chromium good/broken counters, HUD and final game verification. Initial pre-diagnostic-correction run: 52 passed, demonstrating why the adversarial review case was necessary.

Final log: task workspace `work/reliability-v2/python-game-review-final.log`.

Reviewed SHA-256:

- `game_hud.py`: `91a7879570cc43dfca4606d271966b03285b63a083717bfa543e10911874694a`
- `web_tools.py`: `bc287eddaf055815cab37f0cf0d5b7cc5413f5b4aea43acbc1fdc184a499b1ff`

The reviewer did not edit production files. This code approval does not claim that the omitted target of the earlier live run was reconstructed, or that a complete live task now meets its latency target.

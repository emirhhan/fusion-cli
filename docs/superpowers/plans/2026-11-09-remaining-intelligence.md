# Remaining Fusion intelligence work

> Execute inline in the existing isolated worktree under the user's request to finish the remaining list and prior delegation of technical choices. Use test-first implementation and one independent whole-change review.

**Goal:** Reconcile K01–K29 against current evidence and resolve remaining actionable quality defects without changing the free model, quotas, user instructions or installed application before acceptance.

**Spec:** `outputs/fusion-kalan-gelistirme-tam-liste.txt` under `/Users/motogate/Documents/Codex/2026-11-04/fusion-u-a-ve-bir-kullan`, supplemented by v40/v41 and current committed source. Historical evidence remains historical.

**Architecture:** Extend existing prompt measurement, context projection and acceptance infrastructure; do not add another agent framework. Keep code tests, live model results and installed/native acceptance separate.

**Constraints:** Preserve model, thinking preferences, global rules, authority/receipt guards and independent oracle. No publishing, external messages, platform distribution or unapproved service access. Never turn unknown into passed. No live retry without a changed cause. Existing daily 16/global and 8/goal limits remain.

## Tasks

- [ ] K07: create a current K01–K29 inventory with exact newer evidence and remaining acceptance; retain failed runs.
- [ ] K06: RED→GREEN actual request manifest placement and repo/skill counts; retain legacy record semantics, content redaction and disjoint totals. Files: core/prompt_manifest.py, engines/agent/prompt_manifest.py, tests/test_prompt_manifest.py, tests/test_appserver_serialize.py.
- [ ] K15/K23: reproduce cross-task checkpoint restoration and optional-I/O delay, then repair task ownership and bounded optional context work. Do not enable experimental flags. Files: engines/agent/context_projection.py and its lifecycle call sites, tests/test_active_context_projection.py.
- [ ] K27: inspect and extend the existing acceptance gate so current source/model/config/task and independent evidence are required; stale, missing, failed and unmeasured evidence cannot pass. Test held-out invalid inputs first.
- [ ] K04–K25: run affected local regressions and inspect remaining proposals against measured load; implement only supported improvements, record real-service/native and quality-comparison prerequisites separately.
- [ ] Review the complete diff, fix findings, run focused checks, update the inventory with observed results. Package/install only after matching release acceptance.

## Review focus

Legacy manifests must retain their original fields; instructions can occupy mixed roles; pending optional reads must not accumulate workers; a new task in one chat must not inherit an old plan; modified source/config or actor-authored pass flags must not satisfy a release gate.

# Open finding remediation — 4 November 2026

Baseline: `32c6babaf438b310d405b6a323172c18114f3569`.
Authority: user requested fixes for the remaining live/source findings.

## Scope and acceptance

1. Session owner fixes E01/E11/E14: stale requests cannot cancel another turn;
   rejected panel runs never remain running; safe retries use durable effect evidence.
2. Context/data fixes E03–E07: explicit attachment limits, honest removal semantics,
   bounded initial requirement recovery, image journal round trips, reliable discovery.
3. Agent behavior E02/E12/E15 and desktop targeting: affirmative learning evidence,
   relevant delivery cards, task constraints preserved, grounded desktop targets.
4. Parent fixes E08/E09 and remaining E10: locally bundled Inter on secondary
   surfaces, metadata guard before destructive packaging, bounded credential waits.
5. Independent code/Python/React/JavaScript reviews, relevant tests, original-repo
   integration preserving baseline, packaged smoke, installation and live acceptance.

No permission weakening, real data deletion, secrets in logs, publishing or pushing.
Test credentials, transcripts and OS adapters remain synthetic. Live checks use
the existing authorized example.com/Calculator scope.

## Ownership and interface scan

| Tasks | Shared interface | Ruling |
| --- | --- | --- |
| Session / context-data | session attachment and history hooks | Only session worker edits session.py; helper owner supplies exact integration hooks. |
| Agent / context-data | tool offering policy | Context worker owns execution_policy/tool search; agent worker owns loop and requests integration explicitly. |
| Agent / parent | provider construction | Parent owns web_registry/web_session; agent worker consumes compatible provider API. |
| Parent / session | Chrome resources | Parent owns CSS/fonts, session worker owns panel/background JS. |
| Parent / context-data | Remote static resources | Parent owns CSS/font asset routing, context worker owns deletion/history UI only. |
| Session | Admission, terminal state and cancellation | One accepted owner identity must span events, HTTP response and cancel; no fabricated start on busy. |
| Context-data | Persistence and limits | Preserve supported data within shared budgets; reject unsupported excess visibly. Do not purge user data. |
| Agent | Safety and quality | Retain risk review; never solve wrong-target clicks by granting broader permission. |
| Parent | Credential waits and packaging | Avoid unbounded thread spawning and default-executor shutdown hangs; fail metadata guard before deleting old build output. |

Ruling: safe list removal is labelled honestly; implementing irreversible purge is
unnecessary to correct the misleading promise and is outside this remediation.
Ruling: prioritize tested runtime controls over prompt-only promises for known
ownership/targeting failures. Model quality is measured separately from tool success.

## Status

- Session, context/data and agent behavior workers dispatched with isolated ownership.
- Parent implementation pending. Each owner records red/green checks and limits in
  its own remediation report. No all-suite or general model-quality claim is implied.

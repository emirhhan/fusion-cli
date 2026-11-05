# Independent Python review: mixed current research and artifact obligation

Reviewed immutable snapshot: `74fcc573fcd8afd94de7996397aadcfbf93eb603`.
Verdict: **WARNING — two MEDIUM natural-language contract findings below;
no HIGH/CRITICAL Python issues found in this bounded review.**
No production source edited by the reviewer.

## MEDIUM: ordinary English save-to-file request loses artifact obligation

File: `src/fusion_cli/engines/effects/detect.py:447`.
Task: `Save today's weather forecast to weather.html.`
The new direct English mutation recognizer requires the filename adjacent to the
verb (apart from a few articles/type adjectives), so this natural destination
form retains primary effect web_lookup. Independent actual-engine test performs
a successful web_fetch and no file write, then obtains outcome.ok=True with
weather.html absent. Lookup-only evidence therefore satisfies a request that
explicitly asks to save an artifact.

Fix: recognize this bounded verb/object/to-filename form as an artifact mutation
alongside research, preserving question/quote/negation exclusions. Add actual
lookup-only/write-only/both controls for this destination variant, not only
`Create report.html ...`.

## MEDIUM: static research-topic description forces external research

File: `src/fusion_cli/engines/effects/detect.py:491`.
Task: `Create report.html with a static description of how research works.`
The bare research-token fallback creates requires_web_lookup=True, although the
word describes the requested static content rather than a research action.
Write-only evidence cannot complete this ordinary explanation artifact. This
adds unnecessary tool calls/re-prompts and potential task failure.

Fix: keep static-description/concept content outside the bare action fallback,
while retaining explicit research actions and changing public facts. Add the
positive current-report controls alongside this negative.

## Verified behavior and independent evidence

The root's directly covered TR/EN current report forms retain primary workspace
mutation plus separate requires_web_lookup. Actual engine tests reject write-only
and lookup-only evidence and accept both. Exact named source matching remains
separate; generic successful lookup/page-read evidence does not prove semantic
relevance or factual freshness. Browser controls/status and downloads do not
satisfy generic lookup in the reviewed controls. Local input/output target,
URL-path/query literal, quoted translation, no-tools and continuation controls pass.

- Ruff passed for all four scoped source modules and the new mixed-research test.
- Mypy passed for all four source modules.
- Frozen-source baseline: **250 passed in 22.67 seconds** across mixed current /
  named-source contracts, current-fact intent, effect intent/policy and web policy.
- Independent heldouts: **3 failed in 2.59 seconds**: both pure obligations above
  plus the actual-engine lookup-without-artifact completion reproducer.
- External test: task workspace
  `work/reliability-v2/test_python_mixed_research_heldouts.py`.
- Logs: `python-mixed74-review.log`, `python-mixed74-heldouts-red.log` in that directory.
- Sessions 15577 and 93603 completed; no reviewer handles remain active.

SHA-256 fingerprints:

- `agent/execution_policy.py`: `587090937009b731701a26f2f450fe2bd2ad17493ee3b6a79ccd06d45f2ae94b`
- `agent/loop.py`: `46b50de5da64531468e0127013b80713af80c93be289432a9dad0667dfb3aeb8`
- `agent/research_scope.py`: `987925734c79da49d443c900c6e45912213326e3550208cad102882d37057acd`
- `effects/detect.py`: `4c8c2efdec664313bdec1a0d790192490490118bded01503d050ff01d7fabf16`

This review does not require universal NLU or claim all expressions are covered.
The findings are finite ordinary variants of the artifact/research contract.
No original checkout, installed app or package mutation occurred.

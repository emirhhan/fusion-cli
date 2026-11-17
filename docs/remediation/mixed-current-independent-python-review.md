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

## Final bounded re-review: approved follow-up

Reviewed immutable archive: `9b4b8095914ef3d4b79584156ec6bd0d6832a763`.
**APPROVE** the finite artifact/current/source/negation contracts. Both MEDIUM
findings above and the separate general-review negative-file-action cases are
resolved; no HIGH/CRITICAL issues remain in this reviewed scope.

The production follow-up changes only detect.py. Natural save/write-to/as/into
file destinations now retain artifact mutation as the primary obligation plus
independent current-research evidence. Output destinations such as README.md do
not become mistaken local research inputs. Static descriptions of research are
not imperative research actions; static artifacts containing changing public
facts still require source activity. One canonical English file-action verb set
is shared with explicit negation, so all eleven supported verbs respect rejected
instructions without suppressing a separately requested positive action.

Independent frozen-source verification:

- **269 passed in 32.30 seconds**, including all three preserved Python heldout
  failures, all six external general negative-file controls, and the repository
  actual-engine current/named-source/intent regressions.
- Three additional independent actual-engine controls: **3 passed in 3.90
  seconds**. Save today's weather to weather.html with write-only evidence fails;
  source read plus actual file write succeeds; the static research-description
  artifact succeeds with its file write and no web fetch. The preserved earlier
  actual-engine heldout also confirms lookup-only cannot complete the save task.
- Ruff passed for detect.py and the dedicated follow-up test module.
- Mypy passed for detect.py.
- Logs under task workspace `work/reliability-v2/`:
  `python-mixed9b-final-review.log`, `python-mixed9b-actual-controls.log`.
- Additional independent controls:
  `test_python_mixed9b_actual_controls.py` in the same directory.
- Terminal sessions 96709 and 68973 completed exit 0; no reviewer handles remain.

Reviewed detect.py SHA-256:
`b425325c5c8aa45f3966191aa9a82a92b7ea4878afd440c2379539b33ecb9a58`.
The execution_policy.py, loop.py and research_scope.py fingerprints recorded
above remain unchanged from the reviewed 74fcc573 snapshot.

This approval is finite, not a claim of universal language understanding or
semantic source relevance/currentness. No production source, original checkout,
installed app or package was changed by the reviewer.

## Additional modified-filename object follow-up: approved

Reviewed immutable archive: `b9267d240c951937400da9597659d31a79109009`.
**APPROVE** the bounded detect.py follow-up; no new HIGH/CRITICAL findings.

The exact fixture `Create a static report.html containing the latest stable
Python version.` now retains both artifact mutation and research obligations.
The shared filename-object expression permits up to eight modifier words rather
than a business-adjective allowlist. It stops at input/preposition/complement
boundaries, and output-target normalization uses the same object grammar.
Positive researched-artifact fixture groups now assert both obligations, not
only the lookup flag. This review does not claim arbitrary grammar coverage.

Independent verification against archived source/tests:

- **324 passed in 34.66 seconds**, including both preserved general static-current
  artifact regressions, earlier Save/static-concept/negated-verb controls, the
  additional actual Save controls, and twelve modifier × one-sided/both actual
  engine cases. The engine rejects lookup-only and write-only current artifacts
  and accepts both; explanation and input-only controls remain non-mutating.
- Ruff passed for detect.py and all four changed repository test modules.
- Mypy passed for detect.py.
- Independent pure heldouts passed: three unseen modifier phrases (`fully
  self-contained`, `elegant compact data-rich`, `concise independently formatted`)
  preserve both obligations; three from/using/based-on input references do not
  become file outputs.
- Test log: task workspace `work/reliability-v2/python-b926-final-review.log`.
- Reviewed detect.py SHA-256:
  `84099581933ab23fcbe1a29eba27c49c69b5443d1d55bc3c8a3923deddd02b6a`.
- Terminal 55055 completed exit 0; no reviewer terminal handles remain active.

No production source, original checkout, installed application or package was
changed by this reviewer. Existing non-detect backend fingerprints and their
separate scoped approvals remain unchanged by this follow-up.

## Legacy spaced-filename terminal boundary: approved

Reviewed immutable archive: `628c06dfb65a0e49b8b7c3aab67339816e2fb98a`.
**APPROVE** the narrow terminal-boundary follow-up; no HIGH/CRITICAL findings.

The same preposition/complement boundary now applies to both modifier words and
the terminal legacy spaced filename, so topic/input phrases such as `about HTML`,
`of HTML` and `using HTML` do not invent output files. Explicit dotted filenames
including about.html/using.html/of.html remain valid, as does supported legacy
`index html`. The shared boundary is also retained in destination and output
normalization patterns. This is a bounded grammar correction, not universal NLU.

Independent frozen-source evidence:

- **338 passed in 33.27 seconds**, including all six preserved external filename
  boundary controls (with actual engine explanation), both static-current
  regressions, prior Save/static-concept/negated-action controls, actual Save
  controls and repository one-sided/both current/named-source engine coverage.
- Ruff passed for detect.py and the updated filename-object test module.
- Mypy passed for detect.py.
- Ten additional independent pure controls passed: four topic/input negatives
  assert no mutation and no research; five explicit preposition-named dotted
  files preserve mutation; legacy index html preserves mutation.
- Test log: task workspace `work/reliability-v2/python-628-final-review.log`.
- Reviewed detect.py SHA-256:
  `98c6ddb01c9e1ca235ed14b07922a9383dec381002080189cb2d0e4cb1fb28c3`.
- Terminal 71949 completed exit 0; no reviewer terminal handles remain active.

No production source, original checkout, installed app or runtime package was
changed by this reviewer. All approvals retain their separate finite scopes.

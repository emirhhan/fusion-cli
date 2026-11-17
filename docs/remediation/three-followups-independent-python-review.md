# Independent Python review: metadata, report classification and hybrid source gate

Reviewed HEAD: `39ca542e26da96d99e2c1866521d58071decabee`.
No production source edited. Uncommitted contact-form/browser verifier work excluded.

## HIGH — unbounded synchronous rule measurement

Source: `caea6ae106a9c8435e21361fbe3d30597988138b`.
File: `src/fusion_cli/engines/agent/instruction_rules.py:321`.
Verdict: **BLOCK**.

When the prefix exceeds its inclusion limit, `_rule_block(measure=True)` reads
all remaining chunks to EOF and `_rule_content_span` processes each character
in Python. This runs synchronously in agent startup, instruction audits and
settings/RPC inspection. Memory is bounded; input work and latency are not.
A local 16 MiB file included 4 MiB but measured all 16 MiB in 0.715 seconds.
A tracked-read independent test read 8,388,608 characters despite the 4 MiB
inclusion cap. Arbitrarily large/growing files therefore impose arbitrary startup
or UI latency, regressing the previous bounded prefix read.

Fix: impose a hard measurement I/O bound. Beyond it, skip oversized files per
policy, or explicitly report unknown/lower-bound omission rather than presenting
an incomplete count as exact. Do not seek unbounded EOF merely to improve a
diagnostic. Add a tracked-read regression, not just a large finite happy-path test.

The authoritative loaded-file startup event path correctly removes the prior
skipped-rule hook claim. Unicode/body/frontmatter examples pass within finite
measurement; that success does not remove the unbounded-work defect.

## Teacher source reports

Source: `99c7ce2e39ade4b46019c4db3146480cf64aeed8`.
Verdict: **APPROVE**, no HIGH/CRITICAL findings in the bounded consultation scope.

Source URL tokens are removed from workspace filename counting. Read-only source
reports can remain explicitly one-file/dependency-free; API/CDN/runtime/auth/
deployment and multifile controls retain the consultation route. Publication-date
nouns are no longer accidentally treated as publish commands. Actual report
engine test preserves optional teacher access, ordinary self-review and verifier.
This is consultation routing, not a universal language-understanding guarantee.

## MEDIUM — mixed-source parser misses explicit research verbs

Source: `39ca542e26da96d99e2c1866521d58071decabee`.
File: `src/fusion_cli/engines/effects/detect.py:432`.
Verdict for hybrid gate: **WARNING**, no HIGH/CRITICAL findings attributed here.

Both `Research https://example.org/news as the source.` and
`https://example.org/news sayfasını araştır.` appended to an explicit one-file
report yield an empty required_web_urls tuple. The teacher read-only recognizer
accepts these verbs, but `_SOURCE_READING_ACTION` omits them. A successful artifact
write can therefore satisfy the hybrid completion gate without the named source
read. Add these direct research predicates and matching source-contract tests.
The reviewed read/fetch/consult cases do retain workspace mutation priority plus
independent source evidence; unrelated/search-only/failed reads remain insufficient.

## MEDIUM — comma-separated local read lends its verb to a link-only URL

File: `src/fusion_cli/engines/effects/detect.py:448`.
`Read README.md, include a link to https://example.org/news.` wrongly creates a
remote source-read requirement. The corresponding semicolon form does not.
Bind the URL to its own read predicate; an adjacent local-read action must not
turn the link insertion into mandatory fetch. Include a positive/read control
and both comma/semicolon link-only controls.

## Independent evidence

- Ruff passed for six scoped source modules and three new repository test files.
- Mypy passed for all six source modules.
- Ten-file baseline: **183 passed in 21.53 seconds**.
- Four independent adversarial cases: **4 failed in 2.99 seconds**, reproducing
  bounded-I/O failure, both explicit research omissions and comma binding.
- Tests/logs outside repository under task workspace `work/reliability-v2/`:
  `test_review_followup_bounds.py`, `python-followup-bounds-red.log`, and
  `python-three-followups-review.log`.
- Initial baseline invocation referenced a nonexistent test filename and collected
  no tests; corrected invocation above passed. This was test setup, not a defect.
- Terminal handles 45996 (initial setup), 88005 (corrected suite), and 49701
  (independent red probes) are completed; none remain active.

SHA-256 fingerprints:

- `appserver/instructions.py`: `c93ffda0f750d07e1953c1df2f47562f4717e80f76b6bc8ef7d79a35241bd16f`
- `instruction_rules.py`: `2c0cebed5a10c1f00b30df5174746fd151789778f04ee4c46f86dfc76c45e0dd`
- `loop.py`: `24909a9a896c68183f93e98ae7418969a5eb96ec196b8328e958e27b4db15991`
- `teacher_plan.py`: `d1cf710c652a587c5929ee6f36972fc4df576a86bac95d9a73a023266ac4e720`
- `execution_policy.py`: `e259c8514fa2b2c7d93cfcafa1353470dc98962ce3836c64e72e4f282908246b`
- `effects/detect.py`: `93772a22236632ee5252b9247d2d039b0b2619630c9cd05ebd4be3faf95ebfab`

No approval to integrate the blocked metadata source; no installed app, original
checkout or package mutation occurred. Source-read evidence proves reading, not
semantic correctness/freshness of the resulting report.

## Final independent re-review: approved fixes

Reviewed immutable archive: `064646fc` (`src`, `tests`, `pyproject.toml`) in the
reviewer's task workspace `work/pinned-review/064646fc`. This avoids concurrent
uncommitted teacher-budget and contact-form changes; neither was reviewed here.

**APPROVE** the following finite scopes; no HIGH/CRITICAL findings remain:

- `0e384844`: instruction omission measurement is bounded to 4 MiB plus one
  **character**, not UTF-8 bytes, with a cooperative 50 ms diagnostic read loop.
  This is not a hard wall-clock deadline for an individual filesystem read.
  Exact bounded-EOF counts remain exact; cap/time-limited samples explicitly
  expose a lower bound and `trimmed_exact=False`. RPC uses `kirpilan:null` plus
  the lower-bound/exact fields, and audit text/notes preserve that uncertainty.
  Only actually loaded files generate startup hook events.
- `30884bbc`: the three reported mixed-source cases are corrected; source
  research verbs and read-object binding are shared with bounded teacher
  classification. Workspace mutation plus independent named-source evidence
  remains required. Quoted/negated/link-only controls and continuations pass.
- `ab67554d`: prompt permits reporting a passing recovery check in the same
  scope while retaining prior failure and untested-scope honesty; program test
  writes are isolated from real user data instead of imposing a blanket HOME
  reset. Existing compression/constraint tests pass; prompt length is 6096
  characters against the 6100-character budget.
- `b27992c3`: raw teacher opinions remain internal advisory context and visibly
  qualified activity; they are not automatically promoted into final external
  facts or user constraints. Real blocked outcomes and an independently
  unverified-platform warning remain intact.

Independent frozen-source verification:

- Ruff passed for all twelve source modules in the combined review scope.
- Mypy passed for the same twelve source modules.
- **214 passed in 27.22 seconds**, including all four original external
  adversarial tests that previously failed.
- Additional measured Unicode probe: 8 Mi characters / 16 MiB file includes
  4 Mi characters, reports omitted lower bound 1 with exact=False, and completes
  in 0.0083 seconds on this machine. A small Unicode/frontmatter control reports
  the exact five omitted body characters. This comparison supports removal of
  the previous EOF scan; it is not a universal filesystem latency guarantee.
- Independent teacher success/failure controls preserve both outcome status and
  genuine outcome text, disclose unverified platform state and omit imagined
  teacher limitations.
- Full combined test log: task workspace
  `work/reliability-v2/python-pinned0646-review.log`.
- Exact SHA-256 fingerprints for thirteen reviewed files, including the frozen
  `teacher_flow.py` from b27992c3 and prompt text, are saved in task workspace
  `work/reliability-v2/python-pinned0646-source-hashes.json`.
- Terminal session 27040 completed exit 0; no reviewer sessions remain active.

No production source, original checkout, app or package was changed by this
review. The earlier blocked/warning assessments above remain historical evidence;
these scoped fixes resolve them. This is not approval of concurrent contact
verification or teacher timeout-budget work, nor proof of semantic source
freshness or overall Fusion task quality.

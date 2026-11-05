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

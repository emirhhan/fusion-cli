# Independent Python review: startup instruction contract

Source reviewed: `790b396bae161899b661b13f756f02dc0a92294d`.
Verdict: **WARNING — no HIGH/CRITICAL issues; scoped approval with the diagnostic
limitation below.** No production source edited by the reviewer.

Managed-only settings now suppress ordinary user/project rules at discovery and
prevent nested/additional-directory instruction activation. Managed policy files
remain available. Independent checks also verified merge=False loads no files,
normal startup ordering/content is identical to the previous layer+rule assembly,
unscoped instructions appear once, and deferred scoped rules do not contribute
to startup content totals. The new metadata identifies loaded rule files;
startup User/Project event mapping and deduplication tests pass.

## MEDIUM: truncated rules report zero trimmed characters

File: `src/fusion_cli/engines/agent/instruction_rules.py:316`.
`load_unscoped_rules` initializes every new `InstructionFile.trimmed` to zero,
even when the existing rule renderer truncates its content. Independent bounded
probe: three eight-character rules, budget=10 => files with chars=[8,2], visible
truncation note and skipped-rule note, but trimmed_chars=0. The content and
activation budget behavior itself is unchanged; the existing RPC rule rows
already had the same zero placeholder. This does not weaken managed-only or
permission gates, but diagnostics must not be described as exact truncation
accounting. Follow-up: propagate truncation metadata from the renderer and make
the RPC row use the actual loaded-rule metadata where applicable.

A separate preexisting edge remains: the legacy `rule_startup_events(discover_rules)`
path can announce an unscoped rule skipped by the exhausted 4 MiB rule budget.
The normal loaded-file event path now has enough information to avoid that
redundant discovery-based event assembly. This review does not claim that rare
budget-edge hook behavior is fixed.

## Verification

- Ruff passed for all nine scoped source modules and the two repository test files.
- Mypy passed for all nine source modules.
- Combined instruction/URL regression suite: 171 cases passed, including the
  11 independent actual-entrypoint URL controls outside the repository.
- Three additional independent instruction tests passed in 0.68 seconds: real
  managed policy retention plus user/project/add-dir suppression; merge=False;
  exact default content/order/no duplication and deferred exclusion; bounded
  rule truncation/skip behavior.
- Evidence in task workspace `work/reliability-v2/`: the combined log is
  `python-url-instructions-final.log`; additional probes are in
  `test_review_instruction_contract.py`.
- No active reviewer terminal sessions; `11340` completed exit 0.

SHA-256 fingerprints at reviewed snapshot:

- `appserver/instructions.py`: `c943d441b3fc4e809932d12ad6c2390477223e6cfd373fa86dec85c0b8697a8e`
- `instruction_audit.py`: `f91fa22e4d2d2f8c0cbe9772039b8c4a13024d851446e6dda90a110e848918ab`
- `instruction_rules.py`: `0feb947d6dfcecf3000097a0eaf0d74154e2df4f98c17d842887b2079420e5fb`
- `instructions_hook.py`: `c482a7a63e62cfdad923617fe8985cbe1fe3beb0b057cb76eb0cc353b1a072cc`
- `loop.py`: `203558635906913dbc955afad8ad1825b2f3dd084c66ea368fb802923ea67598`
- `project_instructions.py`: `4b992d989425f40cbe21d5c616ae0269261434d2d66d9b36e24564ac0f2c5624`

Approval is limited to the managed activation/default-content/startup metadata
change. No installed application/package or original checkout was changed.

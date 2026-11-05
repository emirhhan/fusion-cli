# Independent Python review: automatic plateau recovery

**APPROVE** the five scoped paths of
`88c33a7e9117881f0611ec2fd095226edc83ff01`. No CRITICAL or HIGH findings remain.
The current bytes match the frozen commit; hashes are in `source-freeze.json`
and `result.json`. The inherited entrypoint fix `05454ff0` is outside this review.

The count-only exploration note no longer becomes a stall signal. Existing
repeated errors, repeat blocking, repeated output and explicit stalled state
remain eligible. The reminder permits necessary targeted reading and no longer
adds a teacher suggestion solely because five calls occurred without a mutation.

Automatic consultation uses one absolute phase deadline covering the registry
execution, including its nested repair/fallback work. It uses the existing cap
and the smaller quarter of any actual external/shared remaining budget. It does
not use or inflate the independent request timeout. Expiry starts no tool; a
timed-out or late returned result is recorded as failed and cannot enable
teacher takeover. The cancellation-count guard preserves external cancellation
when a tool turns it into an ordinary return value or exception.

## Independent checks

- 227 selected project tests passed in 31.47 seconds, with one existing Pydantic
  warning. These include productive reading, actual stall signals, short/expired
  budgets, late cleanup, external cancellation, manual teacher timeout policy,
  observation/desktop routing, shared deadlines and the earlier self-review fix.
- Nine fresh independent probes passed in 1.61 seconds. Paired actual
  `run_agent` flows distinguish five distinct successful file reads followed by
  a targeted edit (zero teacher calls) from an actual five-repeat BLOCKED stall
  followed by the same edit (one consultation).
- The same real stall produces zero consultations for a nested/internal turn,
  teacherless configuration, an unverified teacher session, and a tool allowlist
  excluding `ask_teacher`.
- Two dual-limit probes verify that either authoritative deadline can be the
  tighter limit, that the attempted consultation has correlated assistant/tool
  identities and a failed outcome, and that no takeover is enabled.
- An executor converting external cancellation to `RuntimeError` still leaves
  the caller cancelled, with no successful advisory record.
- Ruff and format checks passed on all four changed Python files; mypy passed
  on `loop.py`. The source text of `_self_review_timeout` and `_self_review`
  remains identical to the previously approved `a7dab5ee` fix. The direct teacher
  executor and shared teacher-flow module were not changed by this commit.

No product or original-checkout edits were made. All owned process handles are
terminal. Final probes use scripted model transports, temporary owned files,
an explicit intro stub, and DNS/socket denial guards. This is not live model or
native acceptance and does not prove arbitrary cancellation-resistant code or
its independent side effects terminate within the phase.

## Retained QA corrections

The first external full-flow probe omitted the repository's intro stub; utility
provider setup reached a Litellm cost-map fetch and was rejected at the socket
denial boundary. Its failure log/XML remain as `independent-intro-error.*`.
The corrected probe stubs that unrelated utility and also denies DNS resolution.

The first repeat-control assumption used only two reads, which correctly return
cached information rather than constituting a blocked stall. That failed
expectation is retained in `independent-cached-read-assumption.*`. The corrected
control explicitly observes the existing BLOCKED boundary before asserting a
consultation. No product change was made to obtain these passing checks.

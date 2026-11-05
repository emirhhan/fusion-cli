# Mixed artifact and requested-source completion

The exact `current_report` acceptance request asks both for `rapor.html` and a
read of the official Python downloads page. An actual-engine negative probe
created the file without any source read and still returned success. Mutation
priority was correct for permissions and artifact work, but it excluded named
source obligations from `ExecutionPolicy.required_web_urls`.

The policy retains its primary mutation effect and separately records explicit,
affirmative source-read URLs. A link destination, quoted example/literal,
translation instruction or rejected source does not add a source read. Explicit
no-tools requests keep tools closed and add no reading obligation; their requested
mutation still cannot be reported completed without actual mutation evidence.
Continuation binds genuine prior user scope, excluding harness notes.

Completion requires both the original action evidence and successful reads of
every specifically requested source. An unrelated page or search query is not a
read of that page. Missing-source recovery uses the existing web-specific note
and truthful source-unverified failure, rather than telling the model to redo a
file mutation or run shell commands. Proof of a model's claimed mutation stays
independent so a missing source does not falsely imply that an actually written
file was absent. No permission, SSRF or optional-teacher changes were made here.

Verification:

- Initial dedicated gate regressions: 11 failed / 13 passed before the fix;
  the original exact-request no-source engine probe also failed before changes.
- 31 dedicated cases pass, including real engine execution with no source,
  unrelated page, search-only evidence, failed source, source without artifact,
  correct source plus artifact, and recovery from unrelated to requested source.
- All affirmative TR/EN coordinated sources are required; a separately linked
  URL does not inherit the read obligation.
- Twelve-file teacher/research/current-fact/execution/action-evidence/format
  regression run: 315 passed in 34.36 seconds. One upstream Pydantic ReadOnly
  warning was emitted by `test_devam_istegi_onceki_kullanici_isinin_kanitini_ister`.
- Ruff check/format and mypy passed for all three changed source files.

The teacher classification fix is separate commit `99c7ce2e`. Both changes need
independent Python/general review and follow-up application build before being
claimed installed. This is evidence of requested-source access, not a general
proof that a model's extracted facts or the page itself are current/correct.

## Independent follow-up: shared source-object binding

Three independent review cases failed before the follow-up: English `Research`
and Turkish `araştır` source requests lost their read obligation, while
`Read README.md, include a link to URL` incorrectly gained one. Source parsing
had reused mutation-oriented coordinated-object merging, joining the comma's
local read and separate link clauses. Source extraction now disables only that
object merge; mutation detection keeps its existing behavior. The affirmative
read/research verb family and its negative forms are shared by the teacher scope
classifier and completion requirement instead of diverging across helpers.

All three independent cases and expanded TR/EN research, negative/local/link
controls pass. The twelve product regression files plus the three independent
follow-up source cases passed 327 tests in 31.70 seconds (one unrelated instruction
measurement case deselected; one upstream Pydantic warning). Ruff and mypy passed.

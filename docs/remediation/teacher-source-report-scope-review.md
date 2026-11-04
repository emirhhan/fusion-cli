# Single-file reports that read sources

The exact `current_report` acceptance request asks for one standalone HTML report,
no external dependencies, and a read of the official Python downloads page.
Preflight teacher classification treated every HTTP URL as an external runtime
dependency and counted its domain/path as workspace files. The Turkish publication
pattern also treated `yayımlanma tarihlerini` (publication dates) as a publish action.
Four source-report classifier regressions failed before changes.

The bounded classifier now requires an explicit read/verify/consult context for
each URL; domains and source document paths are excluded from workspace file
counting. API/CDN/runtime script/data fetching, auth, database, publication,
multiple files, explicit teacher requests and large tasks retain the teacher
route. Quoted examples and negated self-containment cannot supply the affirmative
single-file/no-dependency scope. Publication action patterns distinguish commands
from publication-date nouns.

An actual engine test reads the named source through a network-free tool fixture,
writes the report, keeps the normal verifier and self-review, offers optional
`ask_teacher`, and performs no forced teacher calls. This test does not assert
real-world release facts. Seven relevant teacher/research/current-fact files
passed 155 tests in 13.57 seconds. Ruff check/format and helper mypy passed.

A separate actual-engine negative probe found an existing mixed-effect source
gap: report creation could succeed without reading its requested source because
mutation priority omitted the web-source requirement. The exact failing probe is
preserved in `work/reliability-v2/test_mixed_report_source_gate_red.py`. The parent
has authorized a separate gate fix; this classifier change must not be shipped as
a complete research-quality fix before that gap and independent review are done.
No loop, permissions, source gates or application builds changed in this commit.

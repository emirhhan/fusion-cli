# Cosmetic introductions must remain prose

Date: 2026-11-05

The pinned live counter task returned a cosmetic introduction followed by an
incomplete `write_file` JSON object containing HTML. The intro call offered no
tools, but the response was still published and reinserted into the main request
as a statement the assistant had already made. The raw QA evidence is in
`work/reliability-v2/detailed-pinned-dd/trace.jsonl` in the task workspace.

`intro_paragraph` now skips native tool calls and text containing structured
payload/code markers, including incomplete JSON, canonical emulated tool/payload
markers, HTML/XML, code fences or calls to offered tools. Lists, headings,
multiple paragraphs and excessively long text are also skipped. This is a narrow
cosmetic boundary: the main agent retains its tools and proceeds immediately.
The intro is not retried and no main tool permission is changed.

Validation happens after thinking is stripped and before truncation recovery.
Consequently, a cut-off payload cannot be hidden by keeping an earlier complete
sentence. Valid short prose and existing complete-sentence truncation behavior
are preserved.

Thirteen regressions failed before the implementation. The narration and existing
truncation/image suite then passed all 27 tests. Coverage includes the observed
prose-plus-partial-JSON shape, native calls, canonical incomplete payloads, code,
valid prose, thinking removal and a real-loop test proving rejected text is
neither published nor reinserted while the next real tool creates the file with
exactly the original three provider calls. Ruff check/format and mypy on the
changed production module passed. Full repository and independent code-review
acceptance remain with the integrating parent.

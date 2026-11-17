# Natural file targets, research directives and shared negation

Independent review of `74fcc573` found that `Save today's weather forecast to
weather.html` could finish after lookup alone, while a static description of how
research works unnecessarily required external lookup. General review also found
that newly accepted `save`, `generate` and `edit` actions were missing from the
English negative-action matcher, potentially requiring forbidden file changes.

File action verbs now come from one canonical group used by affirmative object,
direct-filename, destination-filename and negative predicates. Save/write targets
introduced by `to`, `as` or `into` carry an artifact obligation even when the
payload separates the verb from the destination. Those output targets are not
mistaken for local inputs such as README. Independent positive predicates remain
available after rejected actions, including explicit `and create` / `and tell`
clauses; no broad conjunction split detaches ordinary coordinated objects.

The shared source/research classifier recognizes research directives rather than
any noun occurrence of `research`. Concept descriptions do not require lookup;
explicit research commands and current-fact reports still do, including static
HTML containing current public facts. This is not a blanket exemption for the
word `static`, and named-source and generic research continue to share semantics.

Verification:

- Initial own regressions: 9 failed / 4 passed before changes. An additional
  `as README.md` output-source distinction failed before its correction.
- Independent preserved held-outs pass, including the actual Save-task engine
  case that must fail without a file.
- Eleven canonical verbs are tested in negative instructions and with a separate
  positive artifact request. Three actual engine tests prove the negated actions
  do not force files or prevent permitted research/explanations.
- Fourteen product files plus the preserved independent held-out file: 389 passed
  in 36.03 seconds, one upstream Pydantic ReadOnly warning in continuation admission.
- Ruff check/format and detector mypy passed.

Only the detector, dedicated tests and this report changed. Independent final
Python/general review and any application integration remain pending. These
rules enforce the tested action/source contracts; they do not constitute a
universal natural-language intent or source-truth guarantee.

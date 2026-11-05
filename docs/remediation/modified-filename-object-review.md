# Modified filename objects retain artifact requirements

General review of `9b4b8095` found that its own positive fixture, `Create a static
report.html containing the latest stable Python version`, required lookup but
could finish without creating a file. The direct-filename matcher accepted a
fixed vocabulary of modifiers, and that test asserted only lookup.

The filename object grammar now accepts a bounded phrase of arbitrary modifier
words before a filename. Structural preposition/complement boundaries such as
`using`, `from`, `based on`, `about` and `how` prevent an input reference from
being treated as that output object. Artifact detection and output-target
normalization use the same grammar. No business adjective allowlist was extended.
Existing explanatory-question guards and canonical negative/positive action
boundaries remain active.

Positive researched-artifact fixtures now use a shared assertion proving both
obligations: primary mutation, research/source requirement, rejection of write-only
and lookup-only evidence, and acceptance of both. This includes ordinary reports,
the previously weak explicit-research/static-current fixtures, and source-report
teacher-classification fixtures. The new matrix also runs four modifier phrases
through actual engine lookup-only, write-only and both cases, and preserves the
three independent explanatory questions and input-file controls.

Five strengthened policy regressions failed before the change. Final validation
across fifteen product files and two preserved independent review files passed
413 tests in 37.44 seconds. One upstream Pydantic ReadOnly warning remains in the
continuation admission test. Ruff check/format and detector mypy passed.
Independent Python/general review and application integration remain pending;
no original checkout, installed app, runtime package or user config changed.

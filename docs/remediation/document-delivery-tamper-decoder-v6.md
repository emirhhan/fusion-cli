# Defensive test-tampering metadata decoding

The independent TypeScript review reproduced a supported evidence envelope that
claimed verification while reporting one weakened test. The frontend previously
ignored this recognized metadata and displayed a verified document badge.

The decoder now validates supplied `supheli_test_degisikligi` independently:

- `adet` and `zayiflatan` must be nonnegative safe integers; weakening cannot
  exceed the total. Optional recognized `turler` and `yollar` must be string lists.
- A weakened-test signal contradicting `dogrulandi: true` produces the existing
  invalid, blocking envelope, retaining a readable false-claim flag.
- A positive suspicious-test total without weakening makes an otherwise verified
  result unknown. Existing failure/blocking signals remain intact.
- Any supplied valid tamper metadata excludes compact document presentation,
  including zero totals. Zero totals alone retain ordinary verification status.
- Absent metadata retains old-journal compatibility. Unknown future extra keys
  remain ignored. Nested metadata is never copied into the rendered evidence.

The recognized `criteria_count` must also be at least the sum of supplied complete
passed/failed/unverified status totals. Contradictory recognized totals now produce
invalid evidence, rather than a verified badge. Unknown extra count keys do not
participate in that sum.

Validation: 14 newly added regression tests failed before implementation. All
174 tests in the seven focused decoder, event, store, history, identity, card and
activity suites passed afterward, including the existing actual backend projection
fixtures. TypeScript checking and `git diff --check` passed. No dependencies were
installed and no providers, models, native apps or network calls were used.

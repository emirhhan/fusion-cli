# Vision observation grounding — 4 November 2026

## Failure boundary and bounded change

The reported live Calculator screenshot contained `17×23−`, while its visual
description returned `391`, which the main agent treated as verified. The
private screenshot was neither opened nor sent by this investigation. The
independent accessibility observation was supplied by the parent investigation.

`describe_image` previously sent the caller's question directly as the sole
message. A question containing an expected result therefore had no higher
priority contract separating actual display text from calculation or inference.
The helper now sends a fixed system instruction requesting `visible_text`,
`description`, and `uncertainty`, prohibiting calculation/completion and requiring
literal trailing operators. The original question and image remain together in
the user message. Both attempts receive the same messages.

Successful responses now carry the explicit prefix:
`Görsel modelinin gözlemi; bağımsız doğrulama değildir:`. This truthfully identifies
model provenance even when the model ignores the requested fields. No parser
pretends to validate visual correctness. Existing repeat cleanup remains in use.

The existing 200-token first attempt, single 4096-token truncation recovery,
shared 60-second completion deadline, zero provider retries, failure handling,
and cancellation propagation remain unchanged. No model, endpoint, credentials,
provider configuration, or thinking settings changed.

## Actual configured-provider experiment

Six actual requests, without additional retries or fallback, used the existing
configured NVIDIA NIM account and
`nvidia_nim/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`. No private screenshot or
credential contents were logged, saved, or transmitted by the experiment.

Three synthetic 700×530 dark Calculator-like fixtures were drawn locally with
Pillow and local Arial: display literals `17×23−`, `391`, and `0`, white 55px
display text, gray buttons, orange operators. The same question was used in
both variants:

> 17×23 işlemini yaptım. Hesap makinesinde sonuç 391 görünüyor mu? Ekrandaki değeri oku.

Baseline used the previous sole user message; grounded used precisely the
production system instruction plus the same user message. Each request used
4096 tokens, a 60-second timeout, configured utility temperature, and zero
retries. Using the recovery ceiling directly kept this quality comparison to
six requests; it did not test first-attempt token sufficiency.

| Visible literal | Baseline elapsed | Baseline result | Grounded elapsed | Grounded visible_text |
| --- | ---: | --- | ---: | --- |
| `17×23−` | 16.10 s | Read `17×23-`, correctly denied visible 391 | 3.23 s | `17×23−` |
| `391` | 6.67 s | Correctly read 391, also calculated `17 × 23 = 391` | 1.13 s | `391` |
| `0` | 9.05 s | Correctly read 0 | 3.23 s | `0` |

All six returned successful, nontruncated final text. No hidden reasoning was
recorded. The grounded incomplete-expression response was:

```text
visible_text: 17×23−
description: Calculator interface showing the expression "17×23−" on the display; no result value is visible as the calculation is incomplete (equals button not indicated as pressed)
uncertainty: The displayed value is an incomplete expression, not the final result; 391 is not visible on the screen
```

The other grounded responses described the visible number and reported no
uncertainty. Baseline semantic transcription was already correct on all three
synthetic fixtures. Therefore this experiment **did not reproduce the original
false positive** and is not a demonstrated red/green visual-accuracy fix. It
supports a narrower improvement: exact operator preservation and separation of
literal display text from arithmetic on these three examples. The grounded
description still inferred an unpressed equals button, demonstrating that the
instruction is not a reliable inference barrier. The latency observations are
single samples, not a performance claim.

## Verification and remaining acceptance

The existing helper/view-image tests passed before changes: 24 tests. A new
provenance/message-priority/literal-preservation regression failed on the old
implementation, then passed after the change. This mock test verifies transport
and output handling, not model vision quality. The wider relevant helper,
view-image, narration-image, image-flow, image-tools, and vision-apprentice set
passes: 62 tests. Ruff format/check and scoped mypy pass.

The real screenshot false positive remains unproven fixed. A model observation
must not alone establish that a requested GUI task succeeded. When available,
Calculator accessibility display text provides an independent authoritative
application value; reconcile that value with the literal visual observation.
If they disagree, report the disagreement and obtain a new observation rather
than replacing it with the mathematically expected answer. A hard completion
verification contract and a separately authorized live acceptance test remain
necessary before claiming reliable GUI result verification.

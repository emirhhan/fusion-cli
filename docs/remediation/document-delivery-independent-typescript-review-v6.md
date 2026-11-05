# Independent TypeScript review: document delivery presentation

Source pin: `fa8500fc`, specifically frontend changes `a488bbae`, `4a7db5ca`,
`39b459cf` and `24d2628e`. This local review excludes unrelated concurrent work.
No PR merge metadata applies. The six product files inspected matched the pin:
`deliveryEvidence.ts`, `olayMetni.ts`, `history.ts`, `store.ts`, `DeliveryCard.tsx`
and `Conversation.css`.

Verdict: **HOLD for the raw tamper-metadata presentation inconsistency below**.
The normal projected backend path and all specified critical-count, bounded-text,
identity and event controls passed independent checks.

## Finding: supplied test-tampering metadata can still produce a safe document card

At `app/src/protocol/deliveryEvidence.ts:149`, compact document eligibility checks
status, problems, warnings and unmeasured items, but does not inspect the existing
`supheli_test_degisikligi` metadata. This supported schema-1 input is accepted:

```json
{
  "schema_version": 1,
  "dogrulandi": true,
  "engelliyor": false,
  "yanlis_iddia": false,
  "degisen": ["report.html"],
  "degisen_sayisi": 1,
  "sorunlar": [],
  "sunum": "document",
  "supheli_test_degisikligi": {"adet": 1, "zayiflatan": 1}
}
```

The actual decoder result is `kind: supported`, `verified: true`,
`blocking: false`, `presentation: document`. DeliveryCard consequently displays
“Dosya denetlendi”. The backend public projection rejects the same contradictory
weakening-test metadata, and the blueprint excludes test tampering from compact
presentation. Therefore this is a frontend defensive-contract discrepancy,
including for malformed metadata presented through a supported evidence envelope;
it is not a demonstrated bypass of the correctly projected backend path.

The frontend should handle supplied tamper metadata conservatively before it
permits compact presentation, preserving compatibility when the field is absent.
At minimum a known weakening signal must never support a verified document card,
and malformed supplied critical metadata must not become a success indication.

## Nonblocking consistency observation

`criteria_count: 1` combined with `criteria_status_counts: {passed: 2, failed: 0,
unverified: 0}` also retains the document badge. This is contradictory metadata,
but no known failure or unverified outcome is lost. It is recorded as optional
consistency hardening, not an additional blocking finding or expanded feature.

## Fresh validation

- Canonical applicable TypeScript check: `tsc --noEmit`, **EXIT0**.
- Project lint gate: `npm run lint:hooks`, **EXIT0**.
- Seven focused suites covering decoder, events, history, store, message identity,
  delivery card and activity panel: **160 passed, EXIT0**.
- External checks bundled from the pinned source with existing esbuild/Node 22:
  **32 passed, EXIT0**. These cover orphan failed/problem totals, unverified and
  missing outcomes, malformed and future schemas, 32-KiB Unicode bounds,
  redaction, whole paths, live/history identity and proof preservation,
  evidence-only rows, legacy idempotence and neutral incomplete self-review.
- The two observations above were separately recorded as probes rather than
  misreported as passing requirements. No product files were edited.
- No dependency installation, providers, models, native apps, browser profiles or
  network requests were used. All owned test processes terminated.

External evidence:
`work/reliability-v2/document-delivery-independent-ts-v6/independent-checks.cjs`,
`frozen-frontend.cjs` and `independent-results.json` in the task workspace.
Independent React/layout approval remains a separate review; these component
checks are not native desktop acceptance.

# Open fixes React review

Reviewed baseline `32c6baba` through `1c6790b0` and `53bbc64d`, then re-reviewed the focused correction `f2eb2194` at HEAD `351c1c70`, limited to the requested E03/E04 UI files and their tests. Final verdict: **APPROVE — no outstanding CRITICAL, HIGH, or MEDIUM findings.**

## Resolved finding

### Successful browser capture leaves the previous overflow alert visible

File: `app/src/SessionApplication.tsx:2248` (shared successful admission path at `app/src/SessionApplication.tsx:545`).

Issue: Browser capture calls `addAttachments` without clearing `attachmentError`, and successful admission does not clear it either.

Why: With eight image attachments, another browser capture correctly shows the eight-image limit error. Remove one image and capture again: the new image is accepted, but the old limit alert remains in the composer. This tells the user that their successful retry failed. The file picker and both drop routes already clear the prior error before admission.

Fix: Clear the previous attachment error when starting browser image admission, allowing `addAttachments` to replace it on rejection. Keep the DOM drop route's unresolved-file warning intact. Add a browser-capture retry regression covering rejection, removal, successful retry, and alert dismissal.

Resolution verified in `f2eb2194`: `app/src/SessionApplication.tsx:2247` clears the prior error immediately before browser image admission. Rejection still replaces it with the current limit error. The change is confined to the browser route, so successful DOM admission does not erase its unresolved-file warning. Both real integration regressions pass: eight-image rejection followed by removal and successful recapture clears the alert; a mixed valid/unresolved DOM drop adds the valid attachment and retains its warning.

## Verified behavior

- File picker, native drop, DOM drop, and browser capture all reach the shared admission helper. It deduplicates paths before checking 20 total attachments and eight image attachments, matching server count limits. Rejection retains the existing selection; it does not truncate or partially append the new batch.
- The stable callback reads the attachment ref rather than a captured attachment array; consecutive admissions update the ref before scheduling state. Native listener teardown guards callbacks after cleanup. No new hook dependency violation was found.
- Attachment errors are rendered through the composer's alert output. Server-side file existence, supported image extensions, and size checks remain server responsibilities.
- Removal confirmation accurately explains list removal and retained disk records. The client removes rows only after an `ok` response, guards refreshed results with removed IDs, and persists an empty view after removing the final conversation. Existing deletion regressions cover failed removal, refresh, and remount behavior.
- Source inspection of `delete_conversation` confirms that it creates a tombstone and preserves the transcript; transcript reads and listing filter tombstoned conversations. No private transcript data was opened.
- Optional E08 CSS inspection: both surfaces reference local `InterVariable.woff2` assets, which exist; assistant text uses 16px with 1.6 line height. The CSS diff introduces no remote font source or interaction change. Asset delivery is outside this React review.

## Validation

Using Node 22 from `/opt/homebrew/opt/node@22/bin`:

- `npm run lint:hooks`: passed. Hook ordering is enabled globally, and exhaustive dependencies are errors for `SessionApplication.tsx` and `useSessions.ts`.
- `./node_modules/.bin/tsc --noEmit`: passed.
- App, Sidebar, attachmentLimits: 99 tests passed across three files.
- `src/sessions/deletion.test.tsx`: five tests passed.
- Focused re-review: `npm test -- src/App.test.tsx -t 'tarayıcı görselinde sınır reddinden|DOM drop geçerli dosyayı'`: two tests passed, 47 unrelated tests skipped. Prior 104-test, hook lint, and typecheck results above are retained; no full App rerun was needed for this one-line correction.

No full-suite rerun, build, install, model request, network-dependent test, UI automation, or application-code edit was performed. Browser-capture overflow/retry now has integration coverage. The admission helper has direct count boundary tests; exhaustive boundary integration across every entry route remains outside the existing tests.

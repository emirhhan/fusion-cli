# Context and data fixes (E03–E07)

Scope: isolated fusion-deep-fixes worktree; no user data purge or remote calls.

- E03: attachment admission rejects more than 20 files, 8 images, unsupported image extensions, invalid paths, missing files and images above 5 MiB. Image slots count images independently of text files. All UI add routes reject overflow and retain previous selection. Metadata is never silently sliced. A read race returns an explicit retry error through the session owner integration.
- E04: conversation removal says “Listeden kaldır” and explains that the disk record remains. Tombstones still exclude removed conversations from lists and model context. No purge or restore capability is promised; raw transcript preservation is intentional. No existing user files were modified.
- E05: reload remains at most 100 messages. When truncation is necessary, one clearly identified harness note preserves the first user request (up to 8,000 characters) alongside the last 99 messages. The note identifies omitted context and truncation. It is generated from disk on reload once, rather than repeatedly appending the root request. Branch verification uses the same bounded representation.
- E06: journal snapshots preserve valid PNG/JPEG/GIF/WebP data URIs, at most eight images of 5 MiB per message and 56 MiB encoded image content across the journal. Strict base64, MIME/content verification, 40-million-pixel and decompression-bomb checks exclude malformed data. Exclusions produce a recovery note asking for images to be attached again. Remote URLs are neither saved nor fetched. Journal reads are capped at 64 MiB. Atomic 0600 journal permissions remain. Original trace files retain their text/tool-only strict schema. Image pixels may contain private content: persistence now deliberately includes admitted vision input in the existing private local journal.
- E07: ToolSearch is a local discovery capability and does not consume a remote-tool slot. The most recent search selections displace registration-order defaults within the configured external-tool budget. Each search returns at most 12 results (or the smaller current surface budget), including select queries; cumulative discovery does not grow the offered surface. Explicit caller tool restrictions retain precedence. Existing explicit allowlist exceptions retain their previous behavior.

## Verification

Before edits, four local regressions failed: ninth-position image omitted; 21st attachment accepted silently; original requirement absent after 102-message reload; image absent after journal round-trip. A separate discovery regression failed when ToolSearch itself was removed at the 12-tool cap.

After fixes, the focused Python journal, redaction, transcript, attachment and tool-search/profile suites passed (153 tests before the final two boundary tests were added). Nine targeted regression cases also pass, including a corrupt PNG checksum that raises Pillow SyntaxError. Node 22 UI tests pass: 104 tests across App, Sidebar, deletion and attachment limits. TypeScript `tsc --noEmit` and targeted React hook lint pass. An initial direct UI run under the host Node 26 failed because of its localStorage runtime; the supported Node 22 rerun passes.

No build, install, push, real user transcript or network-dependent test was run by this worker. Parent coordinates final independent code, Python, React and TypeScript review. A reviewer caught the existing missing-file error contract; the helper now preserves the bounded basename, with all 22 selected appserver attachment tests passing. Focused mypy (7 source files), Ruff and diff checks also pass.

## React review follow-up

The reviewer found that browser capture retained an old overflow alert after a successful retry. The new App integration test reproduces eight selected PNGs, rejected screenshot capture, removal of one PNG, and successful recapture. It failed with the obsolete alert still present. Browser image admission now clears the previous attachment error before the shared helper validates the selection; a new rejection can replace it. Clearing occurs only in this browser route, preserving the DOM drop route's warning about unresolved files. A separate integration test confirms that a valid dropped image is accepted while an unresolved-file warning remains visible.

## Python review follow-up

Three additional regressions were reproduced before correction. Home expansion can raise `RuntimeError`; attachment metadata now returns a bounded error without including exception details. Image revalidation now raises `ValueError` instead of returning an empty image tuple when a previously admitted image disappears; the existing session error handlers return this error before launching the agent. A session integration test deletes the image immediately after successful metadata admission and verifies rejection.

The original-requirement note now has an explicit producer-assigned `Message.name` marker. Branching recognizes only that marker together with the user role and harness flag, writes one bounded `ConversationOriginalRequirement` metadata event, and restores it as context rather than a user turn. Ordinary internal harness notes remain excluded. Repeated branching retains one original requirement and at most 100 messages. Branch metadata is listable even when the recent tail contains no user turn; rewind counts actual user messages and preserves the requirement context.

The direct image-helper missing/oversized tests now require an explicit exception instead of accepting silent omission. This contract change is intentional: session callers already catch `ValueError` and report it. No session source changes were needed.

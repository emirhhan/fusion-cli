# Shared compact conversation typography

## Cause and change

The earlier compact pass set assistant prose to Inter 16px/24px, but user bubbles still used a local system-font override at 13px with an inherited 20.8px line height. The separate tokens made answers approximately 23% larger than the user's own text. Activity labels had another explicit 14px size, including when moved into the independent portal.

The conversation now shares `--chat-font-family`, `--chat-font-size`, `--chat-line-height`, and `--chat-font-weight`: bundled Inter, .8125rem, 1.5, 400. At the default root size this is 13px/19.5px. User bubbles, narration, assistant prose and work activity labels use the same base. Assistant tables also use that size. Semantic emphasis remains distinct at weight 600 instead of the browser's default bold 700; headings retain their hierarchy and weight 600. Code remains in its existing 12px/13px monospace roles. Tool headers remain 12px. Navigation and the user's accessibility preference are not reset.

This follows the requested equality with the existing 13px user message. The attached screenshot is a visual reference; no unsupported claim of pixel-identical ChatGPT typography is made.

## Verification

- Before the production change, the new parity contract failed in both Chromium and WebKit: user line height was 20.8px instead of the shared 19.5px. The subsequent activity check failed at the actual 14px label instead of 13px.
- The final parity contract passes in both engines: four cases cover user/assistant/narration family, size, normal weight, emphasis, table size, narrow-container size, shared 125% root scaling to 16.25px/24.375px, and activity labels before/after portal transfer.
- Six existing Chromium typography cases passed. Eight light/dark, desktop/narrow/detail snapshots were refreshed and desktop/narrow images visually inspected. The checks retain custom Inter/JetBrains font provenance, Turkish glyphs, hierarchy, code controls, streaming and bounded overflow.
- Ten existing Chromium activity interaction cases passed; four activity snapshots were explicitly refreshed with `--update-snapshots=all` because the ordinary 1% screenshot tolerance could otherwise accept stale expected images.
- Full canonical App test command: 303 files, 2,393 passed. Log: task workspace `work/compact-typography-v2-app-tests.log`. Existing nested `vi.mock` and unavailable canvas notices remain.
- App `tsc --noEmit`, isolated new parity-spec TypeScript check, and `npm run build` passed. Build retains existing chunk-size and static/dynamic import warnings.
- No native package was built or installed by this typography worker. Final installed-app screenshot acceptance remains with the parent integration task.

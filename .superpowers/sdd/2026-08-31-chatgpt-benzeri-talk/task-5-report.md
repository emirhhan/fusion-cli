# Task 5 Report — Native macOS Talk helper window

## Status

Implemented the native-feeling Talk helper header and single rounded translucent surface while preserving the existing close, minimize, mini/normal, microphone, approval, settings, recognition, and session callbacks.

## Changed files

- `app/src/voice/VoiceMode.tsx` — SVG traffic-light glyphs, explicit noninteractive drag regions, transparent root-surface lifecycle marker.
- `app/src/voice/VoiceMode.css` — exact 12 px controls with 8 px spacing, hover/focus glyph behavior, centered title, usable mini layout, 16 px clipped 92% opaque light/dark surface.
- `app/src/voice/VoiceMode.test.tsx` — component contract for control order, stable accessible names, callback preservation, drag exclusion, SVG glyphs, and mini microphone access.
- `app/e2e/talk.visual.ts` — production-size corner transparency, single-surface, viewport containment, control geometry, title centering, microphone, and screenshot assertions.
- `app/e2e/talk.visual.ts-snapshots/talk-mini-listening-light-darwin.png`
- `app/e2e/talk.visual.ts-snapshots/talk-mini-approval-dark-darwin.png`
- `app/src-tauri/src/lib.rs` — transparent helper window with native shadow.
- `app/src-tauri/Cargo.toml` and `app/src-tauri/tauri.conf.json` — enable Tauri's required macOS private API feature for transparent webview windows.
- `artifacts/talk/*.png` — four actual candidate screenshots captured by Playwright at production dimensions.
- `.superpowers/sdd/2026-08-31-chatgpt-benzeri-talk/task-5-report.md` — this report.

`app/src/voice/VoiceWindow.tsx` required no callback or lifecycle change; its existing body transparency/overflow setup remains intact.

## TDD evidence

### RED — component

Command:

```text
cd app && npm test -- VoiceMode.test.tsx
```

Result: exit 1. Vitest ran 11 tests; 2 failed and 9 passed. Expected failures were:

```text
VoiceMode > pencere denetimlerini gerçek eylemlerine bağlar
expected true to be false

VoiceMode > trafik ışıklarını macOS sırasıyla ve hover sırasında çizilecek sabit gliflerle sunar
expected '×−↙' to be ''
```

This proved the old whole-header drag region and text glyph implementation violated the new contract.

### RED — visual

Command:

```text
cd app && npx playwright test e2e/talk.visual.ts
```

Result: exit 1. Four production-size Talk contracts failed, four candidate tests were skipped as expected without `FUSION_CANDIDATE_DIR`, and the mini error microphone test passed. Each contract reported:

```text
Expected: "16px"
Received: "0px"
```

This proved the prior square surface did not satisfy the 16 px clipping contract.

### GREEN — targeted component

Command:

```text
cd app && npm test -- VoiceMode.test.tsx
```

Result: exit 0.

```text
Test Files  1 passed (1)
Tests       11 passed (11)
```

### GREEN — visual contract

Command:

```text
cd app && npx playwright test e2e/talk.visual.ts
```

Result: exit 0.

```text
4 skipped
5 passed
```

The four skips are candidate-only screenshot writers disabled when no destination environment variable is supplied.

### GREEN — screenshot capture

Command:

```text
cd app && FUSION_CANDIDATE_DIR=/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk npx playwright test e2e/talk.visual.ts
```

Result: exit 0.

```text
9 passed
```

### GREEN — full repository gate

Command:

```text
cd app && npm run check
```

Result: exit 0.

```text
Vitest: 65 files passed, 429 tests passed
TypeScript + Vite production build: passed (156 modules transformed)
cargo fmt --check: passed
cargo clippy --all-targets -- -D warnings: passed
cargo test: 71 passed, 0 failed, 3 ignored
```

Vite emitted its existing advisory that some generated chunks exceed 500 kB; it did not fail the build.

## Screenshots

- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/talk-normal-listening-light.png` — 380 × 460 px
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/talk-normal-talking-dark.png` — 380 × 460 px
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/talk-mini-listening-light.png` — 360 × 112 px
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/talk-mini-approval-dark.png` — 360 × 112 px

All four were opened and visually inspected at original resolution. They show one rounded surface without a square backing layer, readable light/dark contrast, correct traffic-light order, a centered normal title, and an accessible mini microphone.

## Native/manual verification

- `npm run tauri dev` compiled and launched the actual `Fusion ile konuş` Tauri helper after enabling the required `macos-private-api` feature.
- The live accessibility tree exposed close, minimize, mini/normal, microphone, and settings controls with the intended Turkish names.
- The green control changed the live window from normal to mini without losing the active `Dinlemeyi durdur` microphone action; the mini tree retained avatar, live status, microphone, and `Paneli büyüt`.
- A local Computer Use drag sequence was attempted against left/center/right header coordinates. The automation service transiently returned `noWindowsAvailable` during the sequence, so pointer movement could not be conclusively observed. Component structure and live accessibility confirm controls are separate from all `data-tauri-drag-region` nodes; visual geometry confirms the explicit left and right drag spans retain width.

## Self-review

- Callback bodies and voice/session state machine code were not changed.
- Traffic lights remain red/yellow/green in macOS order, all exactly 12 × 12 px with 8 px gaps.
- Glyphs have no text fallback in layout and remain at opacity 0 until traffic-light hover or button keyboard focus.
- Header controls have no drag attribute; left, centered title, and right empty regions carry drag attributes.
- Normal title is centered to the full viewport within 1 px, independent of control width.
- Normal and mini controls are asserted inside production viewports; mini microphone remains 40 × 40 px.
- Surface opacity is 92% in both themes and all root layers share a 16 px transparent clip.
- Tauri transparency and native shadow are enabled; no distribution/package artifacts were edited.
- `git diff --check` passed. Unrelated untracked `:memory:.ses`, `app/.superpowers/`, `dagitim/`, and root `index.html` were not touched or staged.

## Concerns

- Native drag movement needs a final human pointer check because local Computer Use lost the window during its multi-drag sequence.
- Enabling transparent macOS webviews requires Tauri's `macos-private-api` feature, now explicitly enabled in both Cargo and Tauri configuration.
- The full build retains the pre-existing Vite large-chunk advisory.

## Fix round 1

### Scope and outcome

The reviewer finding and rejected traffic-light presentation were addressed without changing voice/session lifecycle or the `onClose`, `onMinimize`, `onWideChange`, and `onToggleListen` callback contracts.

- Traffic lights now use macOS close/minimize/zoom colors `#ff5f57`, `#febc2e`, and `#28c840`, 12 px circles, 8 px gaps (20 px center distance), a 14 px title-bar inset, a subtle 0.5 px border, inset highlight/shade, and a small exterior shadow.
- Close/minimize/zoom artwork is dedicated SVG geometry. It is invisible at rest, all three glyphs appear for traffic-light-group hover, and only the keyboard-focused control appears for `:focus-visible`.
- Mini mode now has a deliberate 40 px title bar with controls at the top left. Avatar, status/approval, and 40 px microphone occupy a separate row below it.
- Every left/center/right noninteractive drag region retains `data-tauri-drag-region` and now also invokes Tauri `startDragging()` for a primary pointer. Interactive controls do neither.
- `core:window:allow-start-dragging` was added to the existing `main`/`ses` Tauri capability; its absence was the concrete reason programmatic native dragging could not be authorized.

### Explicit supported-distribution decision

`macOSPrivateApi` remains enabled because it is required for the transparent native helper surface. This is now an explicit product decision instead of a hidden portability loss:

- Supported macOS channel: unsigned/notarized direct-download `.app` and DMG.
- Unsupported channel: Mac App Store.
- The user has no Apple Developer account and does not intend to use the App Store.
- If App Store distribution is ever added, Talk transparency must first be redesigned without private API and both the Cargo feature and Tauri configuration option must be removed.

This decision is documented in `app/README.md`, the user-facing `app/KURULUM.md`, and `docs/superpowers/plans/2026-08-30-gorsel-ve-yayin-kapisi.md`. No files under `dagitim/` were touched.

### RED evidence

Component command:

```text
cd app && npm test -- VoiceMode.test.tsx
```

First RED result: exit 1; 11 tests ran, 1 failed. The new semantic-glyph assertion received `[null, null, null]` instead of `['close', 'minimize', 'zoom']`.

Style command:

```text
cd app && npx playwright test e2e/talk.visual.ts
```

RED result: exit 1; four production-size contracts failed because every control reported `box-shadow: none` instead of native inset treatment. The hover/focus behavior pressure test already passed, proving the existing visibility selector was behaviorally sound before visual refinement.

Native drag boundary command:

```text
cd app && npm test -- VoiceMode.test.tsx
```

Second RED result: exit 1; 12 tests ran, 1 failed. Expected three calls to the native `startDragging` boundary from left/center/right regions, received zero.

Settings isolation command:

```text
cd app && npx playwright test e2e/talk.visual.ts -g talk-contract-talk-normal-listening-light
```

Third RED result: exit 1; the settings-button style probe received a `1px` border instead of `0px`, exposing accidental inheritance from the traffic-light rule. The selectors were split so only traffic controls receive circle styling.

### GREEN evidence

Focused component command:

```text
cd app && npm test -- VoiceMode.test.tsx
```

Result: exit 0; 1 file and 12/12 tests passed.

Focused style/visual command:

```text
cd app && npx playwright test e2e/talk.visual.ts
```

Result: exit 0; 6 tests passed and 4 candidate-writer tests skipped as expected without `FUSION_CANDIDATE_DIR`. This includes exact rendered hue, shadow, size, center-spacing, inset, mini-clearance, rest-hidden, group-hover, and single-focus glyph assertions.

Replacement preview capture command:

```text
cd app && FUSION_CANDIDATE_DIR=/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk npx playwright test e2e/talk.visual.ts
```

Result: exit 0; 10/10 tests passed.

Full gate command:

```text
cd app && npm run check
```

Result: exit 0.

```text
Vitest: 65 files passed, 430 tests passed
TypeScript + Vite production build: passed (156 modules transformed)
cargo fmt --check: passed
cargo clippy --all-targets -- -D warnings: passed
cargo test: 71 passed, 0 failed, 3 ignored
```

Vite retains the existing advisory about generated chunks larger than 500 kB.

Closing sanity verification after the final selector split:

```text
cd app && npm test -- --run src/voice/VoiceMode.test.tsx
cd app && npx playwright test e2e/talk.visual.ts
git diff --check
```

Result: component test 12/12 passed; Talk visual suite 6 passed and 4 candidate-writer tests skipped; `git diff --check` passed. The visual test now waits for computed transparent `html`/`body` surfaces before sampling the contract, removing a React StrictMode effect-transition race observed once during closing verification.

### Replacement preview screenshots

- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/talk-normal-listening-light.png` — 380 × 460 px
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/talk-normal-talking-dark.png` — 380 × 460 px
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/talk-mini-listening-light.png` — 360 × 112 px
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/talk-mini-approval-dark.png` — 360 × 112 px

### Actual native Tauri screenshots

To prevent attachment to the older installed `/Applications/Fusion.app`, an isolated current-worktree app bundle was built with a temporary, uncommitted identifier and the real packaged runtime resources:

```text
cd app && npx tauri build --debug --config /tmp/fusion-task5-native.json --bundles app
```

The build completed and produced `Fusion Task5 Native.app`. Computer Use launched that exact bundle, skipped onboarding, opened Talk, and toggled normal/mini through the live green callback. The screenshots were captured from the native app window and converted to PNG:

- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/native/talk-native-normal-dark.png` — 380 × 460 px
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/artifacts/talk/native/talk-native-mini-dark.png` — 360 × 112 px

Dark native screenshots were feasible under the host's active system theme; light mode is covered by the production-size preview contract. Native screenshot corner sampling reported white compositor pixels at `(0,0)` and dark panel pixels at top center (`#2C2E2B` normal, `#282A27` mini), demonstrating that the rounded corners expose the compositor rather than a square backing rectangle.

### Native movement verification

- CoreGraphics identified the actual normal helper as 380 × 460 at `(530,194)`.
- Real pointer paths were attempted from measured left and center empty-header coordinates using Computer Use. Computer Use returned `noWindowsAvailable` while the gesture was active and CoreGraphics bounds remained `(530,194)`; therefore physical displacement is not claimed.
- A native CoreGraphics mouse path was also attempted, but this terminal process lacks macOS Accessibility event-posting permission; the cursor did not move to the requested endpoint.
- The implementation-level evidence is conclusive: all three regions have the declarative Tauri drag attribute, all three primary-pointer paths call `startDragging()`, control pointer-down calls it zero times, and the required Tauri capability is now granted. A final human pointer movement check remains necessary because this host's automation cannot produce a trustworthy displacement measurement.

### Fix-round self-review

- Traffic-light circles remain exactly 12 × 12 px with 20 px center distance in every production viewport.
- Normal and mini top/left inset is 14–16 px; circles share one vertical center.
- Rest-hidden and hover/focus-visible glyph behavior is tested against computed browser styles.
- Mini title-bar controls have at least 8 px clearance from avatar and microphone; all actions remain inside the viewport.
- Native screenshots came from an isolated current-worktree bundle, not the installed app or Playwright preview. They contain the final traffic-light geometry and rounded-surface work; the normal capture predates the subsequent settings-selector isolation noted below.
- Direct-download-only macOS support and Mac App Store incompatibility are explicit in developer, user, release-plan, and task-report documentation.
- No distribution artifact under `dagitim/` and no unrelated user file was modified.

### Fix-round concerns

- Final physical left/center/right pointer displacement still needs one human check because both available automation routes failed to produce measurable movement, despite corrected native wiring and permission.
- Native screenshots show hover/focus glyphs because the automation pointer/focus remained over the traffic-light group; the default-hidden state is proven by computed-style tests and the replacement preview captures.
- The normal native capture retains the pre-fix settings-button outline because it was captured immediately before the final selector isolation. Native automation was intentionally not rerun during bounded closing verification; current-source settings styling and all production-size preview captures are verified by the focused style contract.
- The existing Vite large-chunk advisory remains.

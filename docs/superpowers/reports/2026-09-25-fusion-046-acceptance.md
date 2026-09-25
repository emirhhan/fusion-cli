# Fusion 0.4.6 acceptance — 25 September 2026

## Current decision

Release is pending live acceptance. The installed `/Applications/Fusion.app` is
still 0.4.5. The separately built 0.4.6 app and DMG are ad-hoc signed; the
packaged-app clean-user smoke test passed. User configuration and the 3.1 GB
data directory have not been replaced or removed.

## Verified

- The final Python suite completed with exit code 0, four existing skips and
  one upstream deprecation warning. Ruff, mypy (333 source files), and the
  package/version focused tests passed after refreshing editable metadata to
  0.4.6.
- The React suite passed 717 tests across 94 files; production TypeScript/Vite
  build passed. Five Settings visual tests passed after their old grid fixture
  was updated for the full-page Settings layout.
- Rust format, clippy and tests passed before the latest Python/React-only
  changes. The final macOS app/DMG build and stable ad-hoc signature passed.
- An isolated Gemini web agent changed an inventory fixture. Its own tests
  passed, and seven protected tests outside its writable root passed: the
  authorized import plus anonymous, viewer, cross-origin, missing CSRF,
  invalid-row atomicity and organization isolation cases.
- That agent's final prose falsely claimed it had edited no files. The
  evidence-based turn report now suppresses that conflicting prose and shows
  the actual changed files and verification command; a regression test covers
  the observed wording.
- Settings were visually inspected at default and 390-pixel widths; the voice
  controls now have a dedicated navigation entry. Sidebar options appear on
  hover as requested in the supplied recording.
- The source UI was clicked through Settings voice, account, models, and browser
  navigation. Sidebar/account tests and a new extension panel integration test
  covered 42 button-flow assertions; the browser settings test passed one more.
  The panel test exercises connect, site permission, page read, prompt send,
  disconnect, and invalid pairing against mocked Chrome and loopback responses.
  TypeScript/Vite build passed after adding the test. These checks do not prove
  the packaged app or installed Chrome extension works end to end.

## Open live gates

- Install the packaged Chrome extension in actual Google Chrome, grant one
  test site, and verify snapshot, click, type, navigation, screenshot and
  side-panel chat end to end. Console/network inspection and broad multi-tab
  controls are not yet implemented; this is not full Claude in Chrome parity.
- Exercise the final packaged app against a permitted desktop application:
  window discovery, focus, accessibility, screenshot, mouse and keyboard;
  verify the denied-permission message as well.
- Check account, projects, chat, model selection, voice hardware, and restart
  persistence in the packaged app. The supplied video does not show every
  narrow/wide conversation state, and full ChatGPT/Codex feature parity is
  not established by source preview tests.
- Only after these gates pass: back up the existing app, replace it without
  touching user data, verify rollback and data continuity, then push and
  publish the appropriate release artifacts.

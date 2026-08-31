# ChatGPT Benzeri Fusion Talk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion Talk'ı sessizlikte metin uydurmayan, canlı yazıya çeviren, kullanıcı araya girdiğinde TTS'yi kesen ve uygulamayla birlikte bütünüyle kapanan ChatGPT benzeri bir sesli sohbet deneyimine dönüştürmek.

**Architecture:** Platform yardımcısı ses etkinliği, segment güveni ve tanıma olaylarını oturum kimliğiyle yayınlar. React'teki tek Talk koordinatörü gönderme, kesme ve yeniden dinleme kararlarını verir. Rust, speech ve TTS yaşam döngülerinin tek sahibidir; macOS yardımcı penceresi aynı koordinatörü kullanan mini ve normal görünümler sunar.

**Tech Stack:** Swift `AVAudioEngine`/`SFSpeechRecognizer`, Tauri 2/Rust, React 19/TypeScript, Vitest, Cargo test, Python contract tests, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-31-chatgpt-benzeri-talk-design.md`

## Global Constraints

- macOS ilk teslimat platformudur; Windows aynı olay sözleşmesini korur.
- Sessizlik, düşük güven veya eski oturum olayı kullanıcı mesajı oluşturamaz.
- Tek sözcüklü gerçek yanıtlar yalnız VAD ve güven kapısını geçerse gönderilir.
- Kullanıcı konuşunca TTS en geç 500 ms içinde durur.
- Kullanıcının açık seçimi olmadan ses buluta gönderilmez.
- Ana uygulama kapandıktan iki saniye sonra speech veya TTS çocuk süreci kalmaz.
- Pencere mini ve normal durumda sürüklenebilir; tek yüzeyli, hafif yuvarlatılmış ve erişilebilirdir.
- Her görsel değişiklik normal/mini ve açık/koyu ekran görüntüleriyle kullanıcıya gösterilir.

---

### Task 1: Tanıma olay sözleşmesi ve ses etkinliği kapısı

**Files:**
- Modify: `desktop_build/listen/main.swift`
- Modify: `desktop_build/listen/README.md`
- Modify: `desktop_build/listen/windows/FusionListen.cs`
- Modify: `tests/test_runtime_bundle.py`

**Interfaces:**
- Produces JSONL `RecognitionEvent`: `{ "tur": "hazir|ses-basladi|kismi|son|ses-bitti|hata", "metin": string, "guven": number|null, "speech_ms": number, "segment": number }`.
- Preserves process-level `session` ownership in Rust; helper events do not invent a second session identifier.

- [ ] **Step 1: Write the failing protocol contract test.** Add a test that builds the macOS helper with a deterministic synthetic-audio test flag and asserts silence yields `hazir` but never `kismi` or `son`; a voiced fixture must yield `ses-basladi` before text and `ses-bitti` after it. Assert every text event includes numeric `guven`, `speech_ms`, and `segment`.

```python
def test_macos_listen_silence_never_emits_transcript(tmp_path: Path):
    result = run_listen_fixture(tmp_path, fixture="silence")
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert events[0]["tur"] == "hazir"
    assert not any(event["tur"] in {"kismi", "son"} for event in events)
```

- [ ] **Step 2: Run the contract test and verify RED.** Run `pytest tests/test_runtime_bundle.py -k 'listen_silence or listen_voiced' -q`. Expected: failure because the current helper emits only `tur` and `metin` and has no deterministic VAD fixture path.
- [ ] **Step 3: Implement RMS-based local VAD and confidence output.** Calibrate the first 300 ms, require at least 250 ms speech, use hysteresis for start/end, and derive confidence from `SFTranscriptionSegment.confidence`. Keep the raw microphone buffer on-device.

```swift
struct TanimaOlayi: Codable {
    let tur: String
    let metin: String
    let guven: Float?
    let speech_ms: Int
    let segment: Int
}
```

- [ ] **Step 4: Gate recognizer output at the helper boundary.** Drop text emitted before `ses-basladi`; never emit `son` for an interval with less than 250 ms detected speech. Do not add a word-specific “Evet” blacklist.
- [ ] **Step 5: Keep Windows protocol-compatible.** Add the same fields to `FusionListen.cs`; values unavailable from the platform must be explicit `null`, never omitted. Keep Windows behavior unchanged beyond the wire contract.
- [ ] **Step 6: Run focused and existing adapter tests.** Run `pytest tests/test_runtime_bundle.py -q` and the Swift signal-cleanup test. Expected: PASS.
- [ ] **Step 7: Commit.** `git commit -m "fix(talk): sessizlik ve dusuk guvenli tanimayi ele"`

### Task 2: React Talk koordinatörü ve güvenilir tur sonlandırma

**Files:**
- Modify: `app/src/voice/voiceMachine.ts`
- Modify: `app/src/voice/voiceMachine.test.ts`
- Modify: `app/src/voice/VoiceWindow.tsx`
- Modify: `app/src/voice/VoiceWindow.test.tsx`
- Modify: `app/src/voice/windowBridge.ts`

**Interfaces:**
- Consumes `RecognitionEvent` from Task 1 inside existing Rust envelope `{ session, line }`.
- Produces one `emitMessage({ kaynak: "kullanici", metin })` per accepted session.
- Adds phases `calibrating`, `hearing`, and `interrupted` to `VoicePhase`.

- [ ] **Step 1: Write failing reducer tests.** Cover silence, low-confidence one-word partial, valid one-word speech, stable full sentence, stale timer, stale session and duplicate final.

```ts
it("sessizlikte gelen düşük güvenli eveti göndermez", () => {
  const listening = voiceMachine(initialVoiceMachine, { type: "START_LISTENING", session: 8 });
  const result = voiceMachine(listening, {
    type: "RECOGNITION", session: 8, event: { tur: "kismi", metin: "Evet", guven: 0.08, speech_ms: 0, segment: 1 },
  });
  expect(result.finalRevision).toBe(0);
  expect(result.phase).toBe("listening");
});
```

- [ ] **Step 2: Write failing integration tests.** Simulate four consecutive sessions with different text, then a silent session. Assert the four texts are distinct and delivered once; silence delivers none. Add a regression case for the current repeated “Evet” symptom.
- [ ] **Step 3: Run tests and verify RED.** Run `cd app && npm test -- voiceMachine.test.ts VoiceWindow.test.tsx`. Expected: missing phases/event shape and current partial timeout accepting low-confidence silence.
- [ ] **Step 4: Move acceptance into a pure gate.** Create a pure `evaluateRecognitionTurn(turn): "wait" | "accept" | "reject"` function colocated with the state machine. Require speech duration, confidence, active session and stable text. The 1.4-second timer may request evaluation but cannot bypass the gate.
- [ ] **Step 5: Make every new listen fresh.** Serialize stop/start, clear transcript candidates and timers before start, and reject every payload whose session differs from `activeSession.current`. Update visible transcript only from the active session.
- [ ] **Step 6: Add actionable rejection state.** A voiced but rejected final shows “Anlayamadım, tekrar söyle” without sending. Silence remains in `listening` and changes no transcript.
- [ ] **Step 7: Run focused tests and build.** Run `npm test -- voiceMachine.test.ts VoiceWindow.test.tsx windowBridge.test.ts` and `npm run build`. Expected: PASS.
- [ ] **Step 8: Commit.** `git commit -m "fix(talk): konusma turlarini guvenle sonlandir"`

### Task 3: Kesilebilir TTS ve gerçek barge-in

**Files:**
- Modify: `app/src/voice/voiceTurn.ts`
- Modify: `app/src/voice/voiceTurn.test.ts`
- Modify: `app/src/App.tsx`
- Modify: `app/src/App.runtime.test.tsx`
- Modify: `src/fusion_cli/appserver/voice.py`
- Modify: `src/fusion_cli/appserver/session.py`
- Modify: `tests/test_voice.py`
- Modify: `tests/test_appserver_session.py`

**Interfaces:**
- Produces `VoiceTurnHandle { id: string; cancel(): Promise<void>; finished: Promise<void> }`.
- Adds protocol request `ses.durdur { tur_id }`; repeated cancellation is idempotent.
- Publishes runtime states `talking`, `interrupted`, then `listening` in that order.

- [ ] **Step 1: Characterize the current `ses.konus` owner.** In `tests/test_voice.py`, record registration, wait, stop and temporary-file cleanup side effects; mock only `subprocess.Popen`, the OS audio player boundary.
- [ ] **Step 2: Write failing cancellation tests.** Start a TTS turn, deliver `ses-basladi`, invoke barge-in, and assert `ses.durdur` completes before the next speech recognition start. Assert a second cancellation succeeds without another player kill.

```ts
expect(order).toEqual([
  "tts:start",
  "speech:detected",
  "tts:cancel",
  "tts:cancelled",
  "recognition:start",
]);
```

- [ ] **Step 3: Run focused tests and verify RED.** Run `cd app && npm test -- voiceTurn.test.ts App.runtime.test.tsx` and `pytest tests/test_voice.py tests/test_appserver_session.py -q`. Expected: current blocking `ses.konus({ bekle: true })` has no turn-scoped cancellation handle.
- [ ] **Step 4: Implement cancellable TTS ownership.** Give each playback a turn id, keep one active player, expose idempotent stop, and guarantee cleanup on normal end, interruption and error.
- [ ] **Step 5: Wire barge-in.** While state is `talking`, retain low-latency VAD. On `ses-basladi`, cancel TTS, discard playback-correlated buffers, transition through `interrupted`, then open a fresh recognition segment without losing the user's first spoken buffer.
- [ ] **Step 6: Verify ordering and latency.** Unit-test event order; instrument monotonic timestamps in development builds and require cancellation acknowledgment within 500 ms.
- [ ] **Step 7: Run React and Python suites.** Expected: PASS with no active player after each test.
- [ ] **Step 8: Commit.** `git commit -m "feat(talk): konusarak sesli yaniti kes"`

### Task 4: Uygulama kapanışında speech ve TTS temizliği

**Files:**
- Modify: `app/src-tauri/src/speech.rs`
- Modify: `app/src-tauri/src/lib.rs`
- Modify: `src/fusion_cli/appserver/session.py`
- Modify: `tests/test_appserver_session.py`
- Test: colocated Rust modules

**Interfaces:**
- Produces idempotent `SpeechManager::stop()` in Rust and calls existing `voice_stop()` from `AppSession.close()` in Python.
- `kapatmayi_onayla`, `RunEvent::Exit`, Talk close and abnormal window destruction all call the relevant cleanup path.

- [ ] **Step 1: Write failing process-lifecycle tests.** Spawn deterministic speech and TTS helper children, invoke Talk close and full application shutdown plans, and assert child PIDs exit within two seconds. Distinguish Talk-only cleanup from full-app cleanup.
- [ ] **Step 2: Run Cargo tests and verify RED.** Run `cd app/src-tauri && cargo test speech shutdown -- --nocapture`. Expected: speech is covered partially, but TTS/runtime playback survives or lacks an owned cleanup contract.
- [ ] **Step 3: Centralize shutdown ordering.** `AppSession.close()` first cancels the active turn, then calls `voice_stop()`, closes managed processes and cancels pending questions. Tauri stops speech before sessions/terminals and exit. Keep every stop idempotent and bounded; `voice.stop()` retains its two-second terminate-then-kill limit.
- [ ] **Step 4: Cover all exit paths.** Connect the same cleanup contract to confirmed main close, Cmd+Q/ExitRequested, final Exit, Talk red button and unexpected Talk window destruction.
- [ ] **Step 5: Run Rust quality gates.** Run `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, and `cargo test`. Expected: PASS and no leaked helper PID.
- [ ] **Step 6: Commit.** `git commit -m "fix(talk): uygulama kapanisinda tum ses kaynaklarini temizle"`

### Task 5: Yerel macOS yardımcı pencere davranışı ve görsel cila

**Files:**
- Modify: `app/src/voice/VoiceMode.tsx`
- Modify: `app/src/voice/VoiceMode.css`
- Modify: `app/src/voice/VoiceMode.test.tsx`
- Modify: `app/src/voice/VoiceWindow.tsx`
- Modify: `app/src-tauri/src/lib.rs`
- Modify: `app/e2e/talk.visual.ts`

**Interfaces:**
- Preserves `onClose`, `onMinimize`, `onWideChange`, `onToggleListen` in both layouts.
- Uses one header drag region; interactive controls explicitly remain outside it.
- Uses one 16 px clipped window surface with no rectangular backing layer.

- [ ] **Step 1: Write failing component tests.** Assert 12 px equal traffic-light controls, macOS ordering, hidden glyphs until hover/focus, a drag region that excludes controls, mini microphone access and stable accessible names.
- [ ] **Step 2: Write failing visual constraints.** At production normal and mini sizes, assert the surface corners are transparent outside the 16 px mask, no second rectangle appears, controls stay within viewport and title spacing is symmetric.
- [ ] **Step 3: Run component/visual tests and verify RED.** Run `npm test -- VoiceMode.test.tsx` and `npx playwright test app/e2e/talk.visual.ts` with the repository's established visual environment.
- [ ] **Step 4: Implement the native-feeling header.** Replace text glyph layout with centered CSS/SVG hover glyphs, set exact control geometry, expand the empty title area across the header and attach `data-tauri-drag-region` to every noninteractive drag child.
- [ ] **Step 5: Implement the single rounded surface.** Clip `html`, `body`, `#root` and `.voice-panel` consistently at 16 px; set Tauri window shadow/transparent background so no square backing remains. Preserve 90–94% opacity and readable light/dark contrast.
- [ ] **Step 6: Verify window movement manually.** Drag from left, center and right empty header areas; verify buttons never drag. Test close, minimize and mini/normal controls.
- [ ] **Step 7: Capture screenshots.** Save light/dark normal and mini PNGs under `artifacts/talk/` and present absolute paths to the user before final packaging.
- [ ] **Step 8: Commit.** `git commit -m "feat(talk): macOS yardimci penceresini cilala"`

### Task 6: Paketli gerçek ses kabulü ve kalıcı dağıtım

**Files:**
- Modify: `app/package.json`
- Create or Modify: `desktop_build/macos/stable_sign_bundle.py`
- Modify: `tests/test_runtime_bundle.py`
- Create: `docs/superpowers/reports/2026-08-31-chatgpt-talk-kabul.md`
- Modify: `docs/NASIL_KULLANILIR.md`

**Interfaces:**
- `npm run bundle:mac` produces an app and DMG whose designated requirement remains `identifier "com.fusion.desktop"` across rebuilds.
- Acceptance report records package checksum, test counts, speech phrases, silence result, interruption latency and process cleanup.

- [ ] **Step 1: Write a failing signing contract test.** Run the signing helper against a disposable app bundle and assert `codesign -dr -` returns the stable identifier requirement. Assert the DMG contains the same signed app identity.
- [ ] **Step 2: Run the test and verify RED.** Expected: the current ad-hoc Tauri build derives designated requirement from a changing cdhash.
- [ ] **Step 3: Implement stable post-bundle signing and DMG replacement.** Sign with the explicit designated requirement, verify deep/strict, replace the DMG app payload, and verify again after mounting read-only. Never alter unrelated mounted volumes.
- [ ] **Step 4: Build and install the package.** Use the canonical macOS bundle command, install `/Applications/Fusion.app`, reset permissions only if the stable identity has no current grant, then perform the user-authorized microphone prompt.
- [ ] **Step 5: Run packaged acceptance.** Speak three distinct Turkish sentences, wait silently for ten seconds, interrupt one Fusion answer, close Talk, then close Fusion. Record exact observed text, interruption latency and `ps` proof that no helper remains.
- [ ] **Step 6: Run all automated gates.** Run Python tests, `npm test`, `npm run build`, Cargo fmt/clippy/test and Playwright Talk visuals. Record exact pass/skip counts without rounding.
- [ ] **Step 7: Deliver screenshots and DMG.** Copy the verified DMG to `dagitim/`, calculate SHA-256 and link the four screenshots plus acceptance report.
- [ ] **Step 8: Commit.** `git commit -m "test(talk): paketli sesli sohbet kabulunu tamamla"`

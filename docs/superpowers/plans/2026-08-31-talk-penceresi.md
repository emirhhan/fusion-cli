# Fusion Talk Penceresi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion Talk'ı normal ve mini görünümde gerçek pencere kontrolleri, güvenilir mikrofon ve aynı sohbete tekil transkripsiyonla çalıştırmak.

**Architecture:** Tauri pencere komutları yerel close/minimize/geometry davranışlarını sağlar. React görünümü köşesiz `%90` opak kabuk kullanır; konuşma makinesi her mikrofon etkileşiminde izlenebilir, tekil bir recognition oturumu yönetir.

**Tech Stack:** React, TypeScript, Tauri 2, Rust, native speech helper, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-31-terminal-izinler-talk-design.md`

## Global Constraints

- Kırmızı kapatır, sarı Dock'a küçültür, yeşil mini/normal geçişi yapar.
- Normal ve mini görünümde mikrofon bulunur.
- Pencere köşesiz, gölgesiz ve `%90` opaktır.
- Başlık sürüklenebilir; etkileşimli düğmeler sürükleme alanı değildir.
- Son transkripsiyon aynı sohbete yalnız bir kez gönderilir.
- Belirsiz konuşma hiçbir zaman onay sayılmaz.
- Her görsel değişiklik ekran görüntüsüyle kullanıcıya gösterilir.

---

### Task 1: Yerel pencere davranışları

**Files:**
- Modify: `app/src-tauri/src/lib.rs`
- Modify: `app/src/voice/windowBridge.ts`
- Modify: `app/src/voice/windowBridge.test.ts`

**Interfaces:**
- Produces: `minimizeVoiceWindow(): Promise<void>` backed by `ses_penceresi_simge_durumu`.
- Preserves: `closeVoiceWindow` and `applyVoiceWindowGeometry`.

- [ ] **Step 1: Write failing Rust and bridge tests** for minimize, close restoring main window, and mini/normal geometry without restarting recognition.
- [ ] **Step 2: Run targeted Cargo/Vitest tests** and confirm failures for the absent minimize command.
- [ ] **Step 3: Implement the native minimize command and bridge**; disable native shadow where supported and keep window decorations off.
- [ ] **Step 4: Run targeted tests, Cargo fmt and clippy**; require exit 0.
- [ ] **Step 5: Commit** with `feat(talk): yerel pencere kontrollerini bagla`.

### Task 2: Köşesiz normal/mini arayüz

**Files:**
- Modify: `app/src/voice/VoiceMode.tsx`
- Modify: `app/src/voice/VoiceMode.css`
- Modify: `app/src/voice/VoiceMode.test.tsx`
- Modify: `app/src/voice/VoiceWindow.tsx`
- Create: `app/e2e/talk-window.spec.ts`

**Interfaces:**
- Consumes: minimize bridge from Task 1.
- Produces: `VoiceMode` props `onMinimize`, `onWideChange`, `onClose`, `onToggleListen` in both layouts.

- [ ] **Step 1: Write failing component tests** proving all three controls are buttons with exact actions, mini mode contains microphone, header has drag region, controls do not, and duplicate right-side controls are absent.
- [ ] **Step 2: Add failing visual contracts** for normal/mini in light/dark themes at production window sizes.
- [ ] **Step 3: Run the targeted tests** and verify the current decorative lights, hidden mini mic and rounded panel fail.
- [ ] **Step 4: Implement the controls and mini layout**. Use semantic buttons, visible focus rings, status text and the same microphone callback in both sizes.
- [ ] **Step 5: Remove border radius/shadow/double frame and set `background: color-mix(... / 90%)` or an equivalent fixed 0.90 alpha**. Ensure `html`, `body`, `#root` and `.voice-panel` fill the rectangular webview.
- [ ] **Step 6: Run component tests, build and Playwright visual tests**. Capture four screenshots and present their absolute paths to the user before proceeding.
- [ ] **Step 7: Commit** with `feat(talk): normal ve mini pencereyi profesyonellestir`.

### Task 3: Güvenilir konuşma tanıma yaşam döngüsü

**Files:**
- Modify: `app/src/voice/voiceMachine.ts`
- Modify: `app/src/voice/voiceMachine.test.ts`
- Modify: `app/src/voice/VoiceWindow.tsx`
- Modify: `app/src/voice/VoiceWindow.test.tsx`
- Modify: `app/src-tauri/src/speech.rs`
- Modify: `app/src-tauri/src/lib.rs`

**Interfaces:**
- Produces: recognition session revision/token carried through start, output and ended events.
- Produces: explicit user-facing error reason and retry path.

- [ ] **Step 1: Write failing lifecycle tests** for listener-before-start, rapid stop/start serialization, stale session output rejection, final text emitted once, mini/normal transition preserving recognition, expected stop, unexpected exit and retry.
- [ ] **Step 2: Reproduce the reported symptom with instrumented fake runtime** and verify at least one test fails on current behavior.
- [ ] **Step 3: Add a monotonically increasing session token** to Rust start/output/end events and ignore stale events in React. Keep one active helper and make stop idempotent.
- [ ] **Step 4: Make microphone click start a fresh session only after permission is granted**; display partial/final text and convert helper failures into actionable Turkish states.
- [ ] **Step 5: Verify final text dispatch** increments exactly one revision and reaches `emitVoiceMessage` once; preserve fail-closed spoken approvals.
- [ ] **Step 6: Run targeted React/Rust tests and perform red-green verification** by temporarily reverting the fix, observing regression failure, restoring it and observing pass.
- [ ] **Step 7: Commit** with `fix(talk): konusma tanima oturumlarini guvenilir yap`.

### Task 4: Paketli mikrofon ve görsel kabul

**Files:**
- Create: `docs/superpowers/reports/2026-08-31-talk-kabul.md`
- Modify: `docs/NASIL_KULLANILIR.md`

**Interfaces:**
- Consumes: complete Talk window and recognition lifecycle.
- Produces: packaged-app acceptance evidence and user-visible screenshots.

- [ ] **Step 1: Build the signed/ad-hoc packaged macOS app and DMG** using the repository's canonical command.
- [ ] **Step 2: In the packaged app, speak one Turkish sentence in normal mode and one in mini mode**; verify each appears exactly once in the same conversation.
- [ ] **Step 3: Verify red/yellow/green behavior, dragging, `%90` opacity, no rounded backing rectangle and no recognition restart during resize**.
- [ ] **Step 4: Save normal/mini screenshots and report their absolute paths to the user**. Record any manual OS permission interaction honestly.
- [ ] **Step 5: Run full React, Rust, Python and visual checks**, record exact counts and DMG checksum, then commit with `test(talk): paketli kabul kanitlarini ekle`.

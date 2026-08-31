# Gerçek Terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion'un sağ paneline ANSI, tam klavye girdisi, yeniden boyutlandırma ve etkileşimli süreçleri destekleyen gerçek PTY terminali eklemek.

**Architecture:** React xterm bileşeni Tauri komutlarıyla Rust `portable-pty` yöneticisine bağlanır. Mevcut Python süreç yöneticisi arka plan görevleri için korunur ve terminal sekmelerinden ayrılır.

**Tech Stack:** React 19, TypeScript, xterm.js, Tauri 2, Rust, portable-pty, Vitest, Cargo test.

**Spec:** `docs/superpowers/specs/2026-08-31-terminal-izinler-talk-design.md`

## Global Constraints

- macOS ve Windows desteklenir.
- Varsayılan kullanıcı kabuğu açılır; cwd yalnız doğrulanmış çalışma klasörüdür.
- ANSI çıktısı temizlenmez veya sağlayıcıya kendiliğinden gönderilmez.
- Mevcut `surec.*` protokolü ve Processes paneli korunur.
- Her davranış önce başarısız testle tanımlanır.

---

### Task 1: Rust PTY yöneticisi

**Files:**
- Create: `app/src-tauri/src/terminal.rs`
- Modify: `app/src-tauri/src/lib.rs`
- Modify: `app/src-tauri/Cargo.toml`
- Test: `app/src-tauri/src/terminal.rs`

**Interfaces:**
- Produces: `TerminalManager::open(cwd, cols, rows)`, `write(id, data)`, `resize(id, cols, rows)`, `close(id)`, `close_all()`.
- Produces: serializable `TerminalSnapshot`, `TerminalOutput`, `TerminalClosed`.

- [ ] **Step 1: Write failing Rust tests** for opening a PTY in a temporary cwd, writing `printf 'fusion-pty-ok\n'`, resizing to `100x40`, interrupting a long command with byte `\x03`, and closing all children.
- [ ] **Step 2: Run `cd app/src-tauri && cargo test terminal -- --nocapture`** and verify failure because `terminal` and `TerminalManager` do not exist.
- [ ] **Step 3: Add `portable-pty` and implement the manager** with a mutex-protected map, cloned reader, writer, child handle, bounded output forwarding, and deterministic cleanup.
- [ ] **Step 4: Expose Tauri commands** named `terminal_ac`, `terminal_yaz`, `terminal_boyutla`, and `terminal_kapat`; emit `terminal://cikti` and `terminal://kapandi` with terminal IDs.
- [ ] **Step 5: Run `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, and `cargo test terminal -- --nocapture`**; require exit 0.
- [ ] **Step 6: Commit** with `feat(app): gercek pty terminal altyapisini ekle`.

### Task 2: xterm köprüsü ve terminal görünümü

**Files:**
- Create: `app/src/processes/terminalBridge.ts`
- Create: `app/src/processes/terminalBridge.test.ts`
- Create: `app/src/processes/XtermSession.tsx`
- Create: `app/src/processes/XtermSession.test.tsx`
- Modify: `app/src/processes/TerminalPanel.tsx`
- Modify: `app/src/processes/TerminalTabs.tsx`
- Modify: `app/src/processes/processes.css`
- Modify: `app/package.json`

**Interfaces:**
- Consumes: Rust commands and events from Task 1.
- Produces: `TerminalRuntime` with `open`, `write`, `resize`, `close`, `onOutput`, `onClosed`.
- Produces: `XtermSession({ terminalId, runtime, active })`.

- [ ] **Step 1: Write failing bridge tests** asserting exact Tauri command names/payloads and event unsubscription.
- [ ] **Step 2: Write failing component tests** with a fake terminal adapter: keyboard bytes call `write`, FitAddon dimensions call `resize`, output reaches `terminal.write`, unmount closes listeners, and Ctrl+C is not intercepted by React.
- [ ] **Step 3: Run `cd app && npm test -- terminalBridge XtermSession`** and confirm failures for missing modules.
- [ ] **Step 4: Install `@xterm/xterm` and `@xterm/addon-fit` and implement the bridge/component**. Keep xterm behind a small adapter so jsdom tests do not depend on canvas layout.
- [ ] **Step 5: Replace the command composer terminal UI** with “Yeni terminal” tabs that open the user shell in the active workspace. Preserve background process output under the Processes tab.
- [ ] **Step 6: Add ResizeObserver fitting, focus, copy/paste, clear, close, status and accessible tab keyboard navigation**. Do not strip ANSI.
- [ ] **Step 7: Run `npm test -- terminalBridge XtermSession TerminalTabs` and `npm run build`**; require exit 0.
- [ ] **Step 8: Commit** with `feat(app): xterm ile etkilesimli terminali bagla`.

### Task 3: Paketli terminal duman testi

**Files:**
- Create: `app/e2e/terminal.spec.ts`
- Modify: `docs/NASIL_KULLANILIR.md`

**Interfaces:**
- Consumes: complete PTY and xterm integration.
- Produces: repeatable terminal acceptance evidence.

- [ ] **Step 1: Add a failing visual/integration contract** for terminal empty, active and ANSI output states; document manual packaged checks for `python3`, `Ctrl+C`, `vim` exit and resize.
- [ ] **Step 2: Run `cd app && npm run test:visual -- terminal.spec.ts`** and confirm the new snapshots/contracts fail before baselines exist.
- [ ] **Step 3: Fix only product defects revealed by the checks**, then capture deterministic reference screenshots.
- [ ] **Step 4: Run app checks and packaged macOS smoke test**, recording exact commands and outputs in a report under `docs/superpowers/reports/`.
- [ ] **Step 5: Commit** with `test(app): gercek terminal kabul kapisini ekle`.

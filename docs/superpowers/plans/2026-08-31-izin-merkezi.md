# İzin Merkezi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion'un açılışta izin istememesini ve macOS izinlerini yalnız ilgili özellik ilk kullanıldığında anlaşılır biçimde yönetmesini sağlamak.

**Architecture:** Yerel bir PermissionCenter durum modeli sistem izinlerini uygulama içi araç onaylarından ayırır. Klasör, mikrofon/konuşma ve Keychain akışları tembel başlar; reddedilen durumlar Sistem Ayarları bağlantısıyla iyileştirilir.

**Tech Stack:** React, TypeScript, Tauri 2, Rust/macOS APIs, Vitest, Cargo test.

**Spec:** `docs/superpowers/specs/2026-08-31-terminal-izinler-talk-design.md`

## Global Constraints

- Açılışta hiçbir macOS izin istemi tetiklenmez.
- Full Disk Access varsayılan olarak istenmez.
- macOS sistem pencereleri otomatik onaylanmaz veya taklit edilmez.
- Yıkıcı Fusion araçları açık kullanıcı onayı istemeye devam eder.
- İzin açıklamaları Türkçe, kısa ve özellik bağlamında gösterilir.

---

### Task 1: İzin durumu ve ilk kullanım kapısı

**Files:**
- Create: `app/src/permissions/types.ts`
- Create: `app/src/permissions/usePermissions.ts`
- Create: `app/src/permissions/usePermissions.test.tsx`
- Create: `app/src/permissions/PermissionPrompt.tsx`
- Create: `app/src/permissions/PermissionPrompt.test.tsx`
- Create: `app/src/permissions/permissions.css`

**Interfaces:**
- Produces: `PermissionKind = "workspace" | "microphone" | "speech" | "keychain"`.
- Produces: `PermissionState = "unknown" | "granted" | "denied" | "restricted"`.
- Produces: `ensure(kind): Promise<boolean>` and `openSettings(kind): Promise<void>`.

- [ ] **Step 1: Write failing tests** proving hook construction performs no request, `ensure` shows one preflight per feature, denial remains visible, and repeated granted calls do not prompt.
- [ ] **Step 2: Run `cd app && npm test -- usePermissions PermissionPrompt`** and verify missing-module failures.
- [ ] **Step 3: Implement the state machine and accessible preflight dialog** with local persistence only for “explanation seen”, never for operating-system grant truth.
- [ ] **Step 4: Add retry and “Sistem Ayarlarını Aç” actions** and Turkish copy explaining why each permission is needed.
- [ ] **Step 5: Run targeted tests and `npm run build`**; require exit 0.
- [ ] **Step 6: Commit** with `feat(app): izinleri ilk kullanim aninda yonet`.

### Task 2: Yerel izin köprüsü ve özellik entegrasyonu

**Files:**
- Create: `app/src-tauri/src/permissions.rs`
- Modify: `app/src-tauri/src/lib.rs`
- Create: `app/src/platform/permissions.ts`
- Create: `app/src/platform/permissions.test.ts`
- Modify: `app/src/dialogs/NewTaskDialog.tsx`
- Modify: `app/src/voice/VoiceWindow.tsx`
- Modify: `app/src/control/ControlPanel.tsx`

**Interfaces:**
- Consumes: UI state model from Task 1.
- Produces: Tauri commands `izin_durumu`, `izin_iste`, `izin_ayarlari_ac`.

- [ ] **Step 1: Write failing Rust tests** for side-effect-free status queries and settings URL selection; write frontend bridge tests for exact command payloads.
- [ ] **Step 2: Run targeted Cargo and Vitest tests** and confirm they fail before implementation.
- [ ] **Step 3: Implement status/request adapters**. On unsupported platforms return an explicit `unsupported` capability instead of pretending permission is granted.
- [ ] **Step 4: Gate folder choice, first Talk activation and key saving** at the point of use. Remove any startup code path that touches protected folders, speech, microphone or Keychain.
- [ ] **Step 5: Keep Fusion's tool approval mode separate** and verify default `auto` plus destructive-operation approval contracts.
- [ ] **Step 6: Run targeted tests, full React build, Cargo clippy and Cargo tests**; require exit 0.
- [ ] **Step 7: Commit** with `fix(app): macOS izin istemlerini gerekli ana ertele`.

### Task 3: Paketli izin kabul testi

**Files:**
- Create: `docs/superpowers/reports/2026-08-31-macos-izin-kabul.md`
- Modify: `docs/NASIL_KULLANILIR.md`

**Interfaces:**
- Consumes: permission center and integrations.
- Produces: resettable manual TCC acceptance procedure and evidence.

- [ ] **Step 1: Document clean-profile checks**: launch causes zero prompts; folder choice asks only if macOS requires it; first Talk explains then requests microphone/speech; denial offers settings; second successful use does not repeat preflight.
- [ ] **Step 2: Build the packaged app and run the checks** without attempting to auto-click system dialogs.
- [ ] **Step 3: Record observed prompt count, bundle identity and screenshots** in the report; treat unexpected startup prompts as failures.
- [ ] **Step 4: Run the complete automated checks** and commit with `test(app): macOS izin kabul akisini belgele`.

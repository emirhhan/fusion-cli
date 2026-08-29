# Fusion macOS Proje Araçları Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion macOS uygulamasındaki Dosyalar, Değişiklikler, Terminal, Süreçler, Testler ve Önizleme sekmelerini gerçek proje verisi ve güvenli işlemlerle çalışır hale getirmek.

**Architecture:** Python `AppSession` proje-kökü sınırındaki dosya/Git/test iş kurallarının sahibi olur ve yapılandırılmış JSON sonuçları üretir. React denetçi bu protokolü oturumun mevcut `ProtocolClient`ı üzerinden tüketir; dosya sistemi veya shell mantığını kopyalamaz. Uzun yaşayan terminal ve geliştirme sunucuları oturuma bağlı süreç kayıtlarıyla yönetilir ve oturum kapanınca temizlenir.

**Tech Stack:** Python 3.11+, asyncio/subprocess, pytest, React 19, TypeScript, Vitest, Tauri 2, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-29-tam-macos-uygulamasi-design.md` §9, §13–15

## Global Constraints

- Her yol oturumun kanonik proje köküne göre çözülür; `..`, mutlak kaçış ve kök dışına çıkan sembolik bağ reddedilir.
- `.env` ve diğer proje dosyaları okunabilir/düzenlenebilir; gizli değerler olay, tanılama ve önizleme günlüklerine kopyalanmaz.
- Büyük dosyalar ve dizinler sınırlı/sayfalı döner; binary içerik metin diye çözümlenmez.
- Doğrudan UI yazımı `expected_sha256` ile iyimser eşzamanlılık denetimi ve oturumluk geri alma anlık görüntüsü kullanır.
- Kullanıcı terminalde açıkça yazdığı komutu çalıştırabilir; agent onay sözleşmesi değiştirilmez.
- Kullanıcıya ait `:memory:.ses` ve `index.html` dosyalarına dokunulmaz.
- Her davranış önce başarısız testle sabitlenir; her görev sonunda ilgili dar kapı ve sonra `make app-check` çalışır.

---

### Task 1: Kök-sınırlı çalışma alanı okuma protokolü

**Files:**
- Create: `src/fusion_cli/appserver/workspace.py`
- Modify: `src/fusion_cli/appserver/session.py`
- Create: `tests/test_appserver_workspace.py`

**Interfaces:**
- Produces: `list_entries(root: Path, data: dict[str, Any]) -> dict[str, Any]`
- Produces: `read_entry(root: Path, data: dict[str, Any]) -> dict[str, Any]`
- Produces protocol requests `proje.listele`, `proje.oku`, `proje.durum`

- [x] Write failing tests proving: deterministic folder-first listing, hidden files included, pagination, UTF-8 read with SHA-256, binary metadata without content, size cap, `..`/absolute/symlink escape rejection.
- [x] Run `.venv/bin/pytest tests/test_appserver_workspace.py -q` and confirm failures are missing behavior rather than fixture errors.
- [x] Implement `workspace.py` with a single `_resolve_inside(root, raw)` boundary and structured Turkish errors.
- [x] Route the three requests in `AppSession._dispatch`; `proje.durum` returns root, Git presence and readable/writable state without scanning the whole tree.
- [x] Run `.venv/bin/pytest tests/test_appserver_workspace.py tests/test_appserver_session.py -q`.
- [x] Commit `feat(app): proje çalışma alanını protokole aç`.

### Task 2: Gerçek dosya ağacı ve okuyucu denetçisi

**Files:**
- Create: `app/src/workspace/types.ts`
- Create: `app/src/workspace/useWorkspace.ts`
- Create: `app/src/workspace/useWorkspace.test.tsx`
- Create: `app/src/workspace/FileExplorer.tsx`
- Create: `app/src/workspace/FileExplorer.css`
- Create: `app/src/workspace/FileExplorer.test.tsx`
- Modify: `app/src/screens/Inspector.tsx`
- Modify: `app/src/App.tsx`

**Interfaces:**
- Consumes: `proje.listele`, `proje.oku`, active session `ProtocolClient`
- Produces: `WorkspaceInspector({ client, root })`

- [x] Write failing component/hook tests for lazy folder expansion, selection, loading/error/empty states, binary file state, keyboard navigation and active-session isolation.
- [x] Run `cd app && npm test -- src/workspace` and observe the expected missing behavior failure.
- [x] Implement typed decoding in `useWorkspace`; never infer protocol payloads with unchecked casts.
- [x] Implement accessible tree/treeitem semantics and a selectable text viewer; do not load child folders until expanded.
- [x] Pass real content into `Inspector.files` from the active session and reset only when session identity changes.
- [x] Run `cd app && npm test -- src/workspace src/screens/Inspector.test.tsx src/App.test.tsx && npm run build`.
- [x] Commit `feat(app): gerçek proje dosyalarını denetçiye bağla`.

### Task 3: Güvenli düzenleme, diff ve geri alma

**Files:**
- Modify: `src/fusion_cli/appserver/workspace.py`
- Modify: `src/fusion_cli/appserver/session.py`
- Modify: `tests/test_appserver_workspace.py`
- Create: `app/src/workspace/ChangesPanel.tsx`
- Create: `app/src/workspace/ChangesPanel.test.tsx`
- Modify: `app/src/workspace/useWorkspace.ts`
- Modify: `app/src/App.tsx`

**Interfaces:**
- Produces protocol requests `proje.yaz`, `proje.degisiklikler`, `proje.geri_al`
- `proje.yaz` consumes `{yol, icerik, expected_sha256}` and returns `{sha256, diff, added, removed}`

- [x] Write failing Python tests for stale-hash rejection, atomic write, unified diff, symlink escape and exact one-file undo; write React tests for visible diff and explicit undo confirmation.
- [x] Run the narrow Python and React tests and confirm red.
- [x] Implement temp-file + atomic replace writes and an in-memory per-session undo journal capped by count and bytes; never store secrets in browser persistence.
- [x] Implement Git-backed changes when `.git` exists and journal-backed changes otherwise.
- [x] Connect Changes panel refresh to successful agent file events and direct edits.
- [x] Run narrow tests, then `make app-check`.
- [x] Commit `feat(app): dosya değişikliklerini ve geri almayı ekle`.

### Task 4: Oturuma bağlı terminal ve süreç yöneticisi

**Files:**
- Create: `src/fusion_cli/appserver/processes.py`
- Modify: `src/fusion_cli/appserver/session.py`
- Create: `tests/test_appserver_processes.py`
- Create: `app/src/processes/types.ts`
- Create: `app/src/processes/useProcesses.ts`
- Create: `app/src/processes/TerminalPanel.tsx`
- Create: `app/src/processes/ProcessesPanel.tsx`
- Create: `app/src/processes/processes.test.tsx`
- Modify: `app/src/App.tsx`

**Interfaces:**
- Produces `surec.baslat`, `surec.yaz`, `surec.kes`, `surec.listele`
- Produces structured events `surec.cikti`, `surec.durum`

- [x] Write failing tests for cwd confinement, stdout/stderr streaming, exit status, independent processes and cleanup on `AppSession.close()`.
- [x] Implement an oturum-owned process registry with stdin and bounded buffers; use process groups so stop/close cannot orphan children.
- [x] Add oturum-scoped terminal, stop actions and process rows; no command text in localStorage.
- [x] Run Python/React narrow tests plus `make app-check`.
- [x] Commit `feat(app): terminal ve süreçleri çalışma alanına bağla`.

### Task 5: Test, build ve Git kanıt yüzeyleri

**Files:**
- Modify: `src/fusion_cli/appserver/processes.py`
- Create: `src/fusion_cli/appserver/project_status.py`
- Create: `tests/test_appserver_project_status.py`
- Create: `app/src/workspace/TestsPanel.tsx`
- Create: `app/src/workspace/GitSummary.tsx`
- Create: `app/src/workspace/project-status.test.tsx`
- Modify: `app/src/App.tsx`

**Interfaces:**
- Produces `proje.git_durum`, `proje.komut_onerileri`, `proje.kanit_calistir`
- Test evidence includes command, exit code, duration, bounded output and timestamp.

- [x] Write failing fixture-repository tests for porcelain status parsing and package/Makefile command discovery without executing package scripts.
- [x] Implement read-only Git status/history and explicit test/lint/build command execution through the process registry.
- [x] Render pass/fail/running state with text and icon, preserve raw output behind disclosure, and offer rerun.
- [x] Run narrow tests and `make check && make app-check`.
- [x] Commit `feat(app): test ve git kanıtlarını görünür yap`.

### Task 6: Asset ve geliştirme önizlemesi, D aşaması yayın kapısı

**Files:**
- Create: `app/src/workspace/PreviewPanel.tsx`
- Create: `app/src/workspace/PreviewPanel.test.tsx`
- Modify: `app/src/workspace/FileExplorer.tsx`
- Modify: `app/src/App.tsx`
- Modify: `app/e2e/preview.tsx`
- Create: `app/e2e/workspace.visual.ts`
- Modify: `Makefile`
- Create: `docs/superpowers/reports/2026-08-29-macos-proje-araclari-sonuc.md`

**Interfaces:**
- Consumes selected file metadata and running process URLs.
- Produces in-app safe previews for images/audio/video/PDF/text and localhost HTTP URLs.

- [x] Write failing tests for supported media types, unsupported fallback, localhost-only embedded URL and external URL refusal.
- [x] Implement object-URL cleanup and sandboxed preview frames; never embed provider/admin secrets in URLs.
- [x] Add visual cases: populated tree, long file, diff, terminal running/error, tests pass/fail, image preview, 920px layout and dark theme.
- [x] Run `make check && make app-check && make app-visual && make app-package`.
- [x] Perform packaged clean-HOME smoke: open project, read file, run a harmless command, stop it, switch sessions, launch preview.
- [x] Write result report and commit `test(app): proje araçları teslimatını doğrula`.

## Phase D Exit Criteria

- [x] Sağ denetçinin yedi sekmesi gerçek aktif oturum verisi gösterir; yer tutucu içerik kalmaz.
- [x] Dosya okuma/yazma/diff/undo proje kökünden kaçamaz ve stale write'ı sessizce ezmez.
- [x] Terminal/süreçler oturumlar arasında karışmaz ve kapanışta çocuk bırakmaz.
- [x] Test/build/Git kanıtı yapılandırılmış, sınırlı ve yeniden çalıştırılabilirdir.
- [x] Asset ve localhost önizlemesi çalışır; dış URL varsayılan gömülmez.
- [x] Python, React, Rust, görsel ve paketli E2E kapıları temizdir.

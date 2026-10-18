# Fusion projects, UI and local model implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one final fresh code review.

**Goal:** Apply the approved project, chat, voice, UI and local-model changes.
**Architecture:** Keep the existing React/Tauri/Python architecture and Kits sidecar. Share project-start actions between creation and navigation, and prepare speech centrally.
**Tech Stack:** React, TypeScript, Tauri, Python, Ollama.
**Spec:** ../specs/2026-10-18-fusion-projects-ui-local-model-design.md

## Global Constraints
- Preserve existing user changes, conversations and project content.
- No forced shutdown of the running app.
- Icons only in a 52px section rail; accessible hover/focus labels.
- Kits remains the visual reference; keep license files and research citations.

## Review Focus
- Failed project starts must preserve the existing session and permit retry.
- A project + must not become an unrelated Desktop chat.
- Emoji sequences must disappear without removing normal digits or Turkish.
- Tooltips and tables must stay usable in narrow windows.
- Local chat success must not be reported as proof of tool-call support.

### Task 1: Project lifecycle
- [x] Add failing behavior tests for create-and-open and same-project new chat, failure/retry.
- [x] Implement shared actions in sessions/projectActions.ts and wire SessionApplication.tsx.
- [x] Preserve specific startup errors; verify project labels and current-project new chat.
- [x] Run project tests and typecheck.

### Task 2: Speech and tables
- [x] Add failing emoji and safe table-linebreak tests.
- [x] Update voice_text.py and Markdown.tsx; remove forced table width and allow long-cell wrapping.
- [x] Run voice-text and Markdown tests.

### Task 3: Visual consistency and Kits link
- [x] Add rail accessible-name/tooltip tests.
- [x] Update MainRail and shared typography using effective Kits styles; align sidebar spacing and theme roles.
- [x] Remove the Kits sidebar source link in fusion-kits App.tsx.
- [x] Validate light/dark wide/narrow views and build both apps.

### Task 4: Local model and delivery
- [x] Install Ollama, download publisher's 9b model, measure chat/stream/cancel/tool behavior.
- [x] Add persistent selectable local model using existing provider/config paths.
- [x] Run app and relevant backend suites, build runtime and signed candidate with current Kits assets.
- [x] Fresh code review, fix actionable findings, document remaining verification limits.

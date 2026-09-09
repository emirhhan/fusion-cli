# Fusion Güvenilirlik ve MCP OAuth Uygulama Planı

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` and implement tasks in order. Every behavior change follows RED → GREEN → refactor. Steps use checkbox syntax for tracking.

**Goal:** Fusion'a güvenli uzak MCP OAuth bağlantısı, kanıta dayalı adım yeniden planlama, görev-yetenek yönlendirmesi, gerçek senaryo ölçümleri ve doğrulanmış macOS yayını eklemek.

**Architecture:** MCP taşıma ve kimlik doğrulaması `mcp_bridge` içinde tek bağlantı hizmetinde toplanır; appserver ve iki ayar yüzeyi bu hizmetin durumunu tüketir. Plan motoru keşif kanıtından uygulama sözleşmesi üretir ve ilerleme parmak izi değişmeyen adımı yeniden kurar. Yönlendirici, sağlayıcı adından bağımsız bir görev gereksinimi ile kalıcı yetenek profilini eşleştirir.

**Tech Stack:** Python 3.11, MCP Python SDK 1.x, httpx, keyring, asyncio, React 19, TypeScript, Vitest, pytest, Tauri/macOS.

**Spec:** `docs/superpowers/specs/2026-09-09-fusion-guvenilirlik-mcp-oauth-design.md`

## Global Constraints

- Mevcut `fusion-runtime-hardening-20260827-022831` dalında çalış; kullanıcıya ait izlenmeyen dosyalara dokunma.
- Eski `name/command/args` MCP kayıtlarını stdio olarak okumaya devam et.
- Token, code, cookie ve sır değerlerini yapılandırmaya veya olay metnine yazma.
- Her üretim değişikliğinden önce davranışı kırmızı testte göster.
- Her görev bağımsız commit olur; son commitlerden sonra tam Python ve uygulama kapıları çalışır.
- Paket yalnız bütün otomatik kapılar geçtikten sonra üretilir ve kurulur.

---

### Task 1: MCP yapılandırma ve bağımsız taşıma oturumları

**Files:**
- Modify: `src/fusion_cli/config/models.py`
- Modify: `src/fusion_cli/config/loader.py`
- Modify: `src/fusion_cli/config/writer.py`
- Modify: `src/fusion_cli/mcp_bridge/client.py`
- Create: `src/fusion_cli/mcp_bridge/transport.py`
- Test: `tests/test_config.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- `McpTransport(str, Enum)`: `STDIO`, `STREAMABLE_HTTP`.
- `McpServerConfig`: existing fields plus `transport`, `url`, `scopes`, `client_id`.
- `McpConnectionStatus`: server, state, tool_count, latency_ms, message.
- `McpClient.connect_server(config)` isolates failures per server; `probe_server` returns status.

- [ ] Add loader/writer tests proving legacy stdio round-trip and HTTP fields without token material.
- [ ] Run those tests and confirm missing fields/serialization fail.
- [ ] Add an MCP test where one connection factory fails and a second connection still registers tools.
- [ ] Run the test and confirm current all-or-nothing enter behavior fails.
- [ ] Implement transport enum/config parsing and writer compatibility.
- [ ] Extract stdio/HTTP stream opening behind a small transport function and keep a per-server `AsyncExitStack`.
- [ ] Add bounded initialize/list timeout and sanitized `probe_server` result.
- [ ] Run focused tests, ruff and mypy; commit `feat(mcp): stdio ve HTTP oturumlarini ayir`.

### Task 2: OAuth PKCE, keyring token deposu ve bağlantı hizmeti

**Files:**
- Create: `src/fusion_cli/mcp_bridge/oauth.py`
- Create: `src/fusion_cli/mcp_bridge/tokens.py`
- Create: `src/fusion_cli/mcp_bridge/service.py`
- Modify: `src/fusion_cli/mcp_bridge/client.py`
- Test: `tests/test_mcp_oauth.py`
- Test: `tests/test_mcp_service.py`

**Interfaces:**
- `KeyringTokenStorage(server_id)` implements MCP SDK `TokenStorage`.
- `LoopbackOAuthFlow.authorize(config)` opens the browser and validates callback state.
- `McpConnectionService.add/test/login/logout/list_status` is the shared app contract.

- [ ] Write token storage tests proving access/refresh token round-trip uses keyring and never YAML.
- [ ] Write deterministic OAuth tests for metadata discovery through SDK, PKCE redirect, state mismatch, timeout, refresh and logout.
- [ ] Run and observe failures because OAuth components do not exist.
- [ ] Implement token storage using the existing credentials/keyring boundary.
- [ ] Wrap MCP SDK `OAuthClientProvider`; open the system browser and host a loopback callback on `127.0.0.1` with a random free port.
- [ ] Reject non-loopback plaintext HTTP URLs and redact OAuth errors.
- [ ] Implement connection service and status cache invalidation.
- [ ] Run focused tests and static checks; commit `feat(mcp): OAuth PKCE ve guvenli token deposu ekle`.

### Task 3: Masaüstü MCP giriş ve sağlık arayüzü

**Files:**
- Modify: `src/fusion_cli/appserver/connectors.py`
- Modify: `src/fusion_cli/appserver/session.py`
- Modify: `src/fusion_cli/appserver/protocol.py`
- Modify: `src/fusion_cli/gateway/app.py`
- Modify: `app/src/settings/Connectors.tsx`
- Modify: `app/src/settings/Settings.css`
- Modify: `app/src/settings/Settings.test.tsx`
- Test: `tests/test_connectors.py`
- Create: `tests/test_appserver_connectors.py`

**Interfaces:**
- Protocol requests: `baglanti.ekle`, `baglanti.dogrula`, `baglanti.giris`, `baglanti.giris_durumu`, `baglanti.cikis`, `baglanti.sil`.
- Row JSON includes `tasima`, `url`, `durum`, `arac_sayisi`, `mesaj`; secret fields are absent.

- [ ] Write backend tests for HTTP validation, status, login dispatch, logout and live config refresh.
- [ ] Run and observe missing protocol behavior.
- [ ] Write React tests for transport switch, HTTP URL, “Giriş yap”, pending, connected tool count and retry errors.
- [ ] Run and observe UI failures.
- [ ] Connect appserver and gateway routes to `McpConnectionService`.
- [ ] Replace command-only form with accessible transport-aware form and status cards; preserve stdio workflow.
- [ ] Poll only while login is pending and cancel polling on unmount.
- [ ] Run focused Python/React tests and checks; commit `feat(app): MCP OAuth girisini ve sagligini yonet`.

### Task 4: Keşif sözleşmesi, ilerleme parmak izi ve adım yeniden planlama

**Files:**
- Modify: `src/fusion_cli/core/execution_plan.py`
- Modify: `src/fusion_cli/engines/agent/plan_generation.py`
- Modify: `src/fusion_cli/engines/agent/plan_parser.py`
- Modify: `src/fusion_cli/engines/agent/plan_runner.py`
- Modify: `src/fusion_cli/engines/agent/plan_checkpoint.py`
- Modify: `src/fusion_cli/engines/agent/prompts/execution_plan.md`
- Create: `src/fusion_cli/engines/agent/progress.py`
- Create: `src/fusion_cli/engines/agent/replan.py`
- Test: `tests/test_plan_parser.py`
- Test: `tests/test_plan_runner.py`
- Test: `tests/test_plan_repair.py`
- Test: `tests/test_plan_resume.py`

**Interfaces:**
- Plan steps expose `phase: discovery|execution` and `revision` with backward-compatible defaults.
- `progress_fingerprint(step, outcome, verification, touched)` returns stable SHA-256.
- `replan_failed_step(plan, failed_id, evidence, provider)` preserves verified independent steps.

- [ ] Add parser test rejecting a discovery step that requires a future artifact as its own effect.
- [ ] Add runner test where an incorrect asset target repeats once, triggers replan, changes target and preserves the completed discovery step.
- [ ] Add runner test where identical replan result pauses immediately with a precise reason instead of spending the full budget.
- [ ] Add checkpoint round-trip test for phase, revision and last progress fingerprint.
- [ ] Run focused tests and verify current behavior fails.
- [ ] Implement phase parsing and prompt contract.
- [ ] Implement fingerprinting from normalized evidence, changed/touched paths and tool outcomes.
- [ ] Implement one bounded replan call for failed/dependent steps and checkpoint persistence.
- [ ] Run plan suites and static checks; commit `fix(plan): kanitla adimi yeniden kur ve donguyu erken kes`.

### Task 5: Gerçek asset doğrulaması ve lisans manifesti

**Files:**
- Create: `src/fusion_cli/core/assets.py`
- Modify: `src/fusion_cli/engines/agent/step_verification.py`
- Modify: `src/fusion_cli/engines/agent/prompts/execution_plan.md`
- Test: `tests/test_asset_evidence.py`
- Test: `tests/test_plan_runner.py`

**Interfaces:**
- `inspect_image_asset(path)` returns dimensions, format, bytes and validity findings.
- Asset verification requires a sibling/project manifest entry with source URL and license.

- [ ] Write tests rejecting empty, corrupt, extension-mismatched and 1x1 placeholder images.
- [ ] Write a test accepting a real fixture PNG plus source/license manifest.
- [ ] Run and observe missing verifier failure.
- [ ] Implement standard-library image header inspection for PNG/JPEG and manifest validation without new heavyweight dependency.
- [ ] Connect checks only when a plan criterion declares an image asset, leaving ordinary file checks unchanged.
- [ ] Run focused tests and checks; commit `feat(verify): gercek asset ve lisans kanitini dogrula`.

### Task 6: Görev gereksinimi ve sağlayıcı yetenek yönlendirmesi

**Files:**
- Create: `src/fusion_cli/providers/capabilities.py`
- Modify: `src/fusion_cli/config/models.py`
- Modify: `src/fusion_cli/config/loader.py`
- Modify: `src/fusion_cli/config/writer.py`
- Modify: `src/fusion_cli/config/model_select.py`
- Modify: `src/fusion_cli/core/routing_strategy.py`
- Modify: `src/fusion_cli/providers/web_registry.py`
- Test: `tests/test_provider_capabilities.py`
- Test: `tests/test_provider_factory.py`
- Test: `tests/test_web_execution_policy.py`

**Interfaces:**
- `TaskRequirements`: tools, native_tools, images, web, long_running, exclusive_session.
- `ProviderCapabilities`: corresponding support plus last evaluation state/time.
- `select_compatible_model(candidates, requirements)` filters mandatory capabilities before ranking.

- [ ] Test that Gemini Web is excluded from a long image+multi-tool mutation task.
- [ ] Test that a user-selected incompatible model returns a clear preflight issue.
- [ ] Test fallback never drops a mandatory capability and browser profiles are exclusive.
- [ ] Run and observe missing capability filtering.
- [ ] Implement profiles from provider definitions and web session evaluation fields.
- [ ] Infer requirements conservatively from attachments, enabled tools and execution profile.
- [ ] Integrate selection before plan generation and expose the reason in status/events.
- [ ] Run routing/web suites and static checks; commit `feat(route): modeli dogrulanmis yetenekle sec`.

### Task 7: Production değerlendirme profili

**Files:**
- Create: `evals/suites/production.yaml`
- Create: `evals/fixtures/oauth_mcp_server.py`
- Create: `evals/fixtures/godot_project/`
- Modify: `evals/profiles.py`
- Modify: `evals/cli.py`
- Create: `tests/test_production_eval.py`
- Modify: `docs/YETENEKLER.md`

**Interfaces:**
- `production` profile reports run success and strict repeated-task success separately.
- Mandatory local scenarios use deterministic providers/fixtures; live Meta remains an explicit manual smoke check.

- [ ] Write suite validation tests for five required scenario families and three repetitions.
- [ ] Write fixture integration test for OAuth initialize/list/call/logout.
- [ ] Run and observe missing profile/fixtures.
- [ ] Add production suite and local fixture runners for Godot asset, OAuth, replan, large artifact and concurrent conversation isolation.
- [ ] Add report fields that prevent the run rate being presented as strict reliability.
- [ ] Document exact automated and manual coverage.
- [ ] Run production profile locally; fix only reproducible product failures through a new RED/GREEN cycle.
- [ ] Commit `test(eval): gercek Fusion senaryolarini olc`.

### Task 8: Tam doğrulama, inceleme, yayın ve kurulum

**Files:**
- Modify only files required by verification findings.
- Create: `docs/superpowers/reports/2026-09-09-fusion-guvenilirlik-mcp-oauth-sonuc.md`
- Update existing release manifest/build outputs through repository scripts.

- [ ] Review complete diff for security, swallowed failures, React hook cleanup and backward compatibility.
- [ ] Run `ruff format --check`, `ruff check`, `mypy`, full pytest and deadlock gate using repository commands.
- [ ] Run application TypeScript, Vitest, Rust fmt/clippy/test and production build gates.
- [ ] Run the deterministic production profile three repetitions.
- [ ] Write result report with exact commands, counts and any remaining external/manual limitation.
- [ ] Commit verification/report fixes.
- [ ] Push the current feature branch and verify remote HEAD equals local HEAD.
- [ ] Build signed `/Applications/Fusion.app`, verify its embedded runtime matches source HEAD, launch smoke test.
- [ ] Create a DMG named with the final commit; remove older Fusion DMGs from Desktop and reveal the new DMG in Finder.

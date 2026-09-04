# Otomatik Profesyonel Yürütme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion'ın basit görevleri hızlı, karmaşık veya sonradan büyüyen görevleri kullanıcı ayarı olmadan planlı, checkpoint'li ve doğrulanmış biçimde yürütmesini sağlamak.

**Architecture:** Mevcut sınıflandırıcı, `run_agent`, changeset, doğrulama ve olay altyapısı genişletilir. Saf `core` modelleri ile `engines/agent` orkestrasyonu ayrılır; checkpoint adaptörü `memory` katmanında kalır. Yeni kurulum ve eski boolean config varsayılan `auto` davranışına taşınır.

**Tech Stack:** Python 3.11+, frozen dataclass, asyncio, YAML config, pytest, Ruff, mypy, Tauri/React masaüstü paketleme.

**Spec:** `docs/superpowers/specs/2026-09-04-otomatik-profesyonel-yurutme-design.md`

## Global Constraints

- Docstring, yorum, log, hata ve kullanıcı metinleri Türkçe; tanımlayıcılar İngilizce olmalıdır.
- `core` yalnız stdlib kullanmalıdır; katman yönü `cli → ui → engines → memory/config/core` korunmalıdır.
- İkinci agent veya paralel workflow motoru yazılmamalıdır; mevcut `run_agent` ve workflow yolu genişletilmelidir.
- Temiz kurulum ve eski `workflow_mode: false` değeri `auto` kullanmalıdır.
- Yıkıcı veya idempotent olmayan işlem otomatik tekrarlanmamalıdır.
- Her üretim davranışı önce doğru nedenle kırılan testle eklenmelidir.
- Her görev sonunda `ruff check`, `mypy` ve görevde listelenen pytest komutları; her faz sonunda tam pytest çalışmalıdır.
- Son kabul güncel HEAD'den paketlenen ve `/Applications/Fusion.app` içine kurulan uygulamada yapılmalıdır.

---

### Task 1: Tipli yürütme modu ve eski config göçü

**Files:**
- Create: `src/fusion_cli/core/execution_mode.py`
- Modify: `src/fusion_cli/config/models.py`
- Modify: `src/fusion_cli/config/defaults.yaml`
- Modify: `src/fusion_cli/config/loader.py`
- Test: `tests/test_config.py`
- Test: `tests/test_config_writer.py`

**Interfaces:**
- Produces: `ExecutionMode(Enum)` değerleri `AUTO`, `ALWAYS`, `OFF`
- Produces: `normalize_execution_mode(value: object) -> ExecutionMode`
- Produces: `RuntimeConfig.workflow_mode: ExecutionMode`

- [ ] **Step 1: Eski boolean ve yeni string değerleri için kırılan testleri yaz**

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [(False, ExecutionMode.AUTO), (True, ExecutionMode.ALWAYS),
     ("auto", ExecutionMode.AUTO), ("always", ExecutionMode.ALWAYS),
     ("off", ExecutionMode.OFF)],
)
def test_workflow_mode_eski_ve_yeni_degerleri_normalize_eder(tmp_path, raw, expected):
    config = load_config(_config_with_runtime(tmp_path, workflow_mode=raw))
    assert config.runtime.workflow_mode is expected
```

- [ ] **Step 2: Testleri çalıştır ve enum olmadığı için kırıldığını doğrula**

Run: `.venv/bin/pytest tests/test_config.py tests/test_config_writer.py -q`

- [ ] **Step 3: Enum, loader normalizasyonu ve `auto` varsayılanını uygula**

```python
class ExecutionMode(Enum):
    AUTO = "auto"
    ALWAYS = "always"
    OFF = "off"

def normalize_execution_mode(value: object) -> ExecutionMode:
    if value is False:
        return ExecutionMode.AUTO
    if value is True:
        return ExecutionMode.ALWAYS
    try:
        return ExecutionMode(str(value).strip().lower())
    except ValueError as exc:
        raise ConfigError("Bilinmeyen workflow_mode değeri...") from exc
```

- [ ] **Step 4: Config testleri ve kalite kapısını çalıştır**

Run: `.venv/bin/pytest tests/test_config.py tests/test_config_writer.py -q && .venv/bin/ruff check src tests && .venv/bin/mypy src`

- [ ] **Step 5: Task 1 altında listelenen dosyaları commit et**

```bash
git add src/fusion_cli/core/execution_mode.py src/fusion_cli/config/models.py src/fusion_cli/config/defaults.yaml src/fusion_cli/config/loader.py tests/test_config.py tests/test_config_writer.py
git commit -m "feat(yurutme): otomatik workflow modunu varsayilan yap"
```

### Task 2: Hibrit başlangıç rotası

**Files:**
- Create: `src/fusion_cli/engines/agent/execution_route.py`
- Modify: `src/fusion_cli/engines/agent/execution_policy.py`
- Test: `tests/test_execution_route.py`

**Interfaces:**
- Consumes: `TaskClassification`, `ExecutionPolicy`, `ExecutionMode`
- Produces: `ExecutionRoute(Enum)` değerleri `FAST`, `FAST_PROMOTABLE`, `WORKFLOW`
- Produces: `ExecutionRouteDecision(route, reasons)`
- Produces: `choose_execution_route(task, classification, policy, mode) -> ExecutionRouteDecision`

- [ ] **Step 1: Basit, karmaşık, dış etkili, belirsiz ve always/off rota testlerini yaz**

```python
def test_feature_varsayilan_olarak_workflow_secer():
    decision = choose_execution_route("özellik ekle", feature_classification(), complex_policy(), ExecutionMode.AUTO)
    assert decision.route is ExecutionRoute.WORKFLOW
    assert "karmaşık görev türü" in decision.reasons

def test_kisa_sohbet_hizli_yolu_secer():
    decision = choose_execution_route("merhaba", general_classification(), simple_policy(), ExecutionMode.AUTO)
    assert decision.route is ExecutionRoute.FAST
```

- [ ] **Step 2: Testin eksik modül nedeniyle kırıldığını doğrula**

Run: `.venv/bin/pytest tests/test_execution_route.py -q`

- [ ] **Step 3: Saf karar matrisi uygula; istem uzunluğunu tek ölçüt yapma**

- [ ] **Step 4: İlgili testler, Ruff ve mypy çalıştır**

Run: `.venv/bin/pytest tests/test_execution_route.py tests/test_web_execution_policy.py tests/test_classifier_v2.py -q && .venv/bin/ruff check src tests && .venv/bin/mypy src`

- [ ] **Step 5: Commit et**

```bash
git add src/fusion_cli/engines/agent/execution_route.py src/fusion_cli/engines/agent/execution_policy.py tests/test_execution_route.py
git commit -m "feat(yurutme): hibrit gorev rotasini ekle"
```

### Task 3: Çalışma sırasında tek yönlü yükseltme

**Files:**
- Create: `src/fusion_cli/engines/agent/promotion.py`
- Modify: `src/fusion_cli/engines/agent/loop.py`
- Modify: `src/fusion_cli/core/tools.py`
- Test: `tests/test_execution_promotion.py`
- Test: `tests/test_agent_loop.py`

**Interfaces:**
- Produces: `ExecutionSignals(pending_todos, touched_components, tool_families, has_dependency, needs_repair, needs_verification, budget_pressure)`
- Produces: `should_promote(signals: ExecutionSignals) -> PromotionDecision`
- Produces: `PromotionContext(task_summary, touched_paths, pending_todos, tool_evidence)`

- [ ] **Step 1: Her yükseltme tetiği ve tek yönlülük için parametreli test yaz**

```python
@pytest.mark.parametrize("signals", promotion_signal_fixtures())
def test_her_karmaşıklık_sinyali_workflowa_yukseltir(signals):
    assert should_promote(signals).should_promote is True
```

- [ ] **Step 2: Testlerin eksik karar modülü nedeniyle kırıldığını doğrula**

Run: `.venv/bin/pytest tests/test_execution_promotion.py -q`

- [ ] **Step 3: Saf sinyal değerlendirmesini ve loop içindeki yükseltme çıkışını uygula**

- [ ] **Step 4: Loop entegrasyon testlerinde hızlı turun doğru bağlamla workflow'a devrettiğini kanıtla**

- [ ] **Step 5: İlgili kapıları çalıştır ve commit et**

Run: `.venv/bin/pytest tests/test_execution_promotion.py tests/test_agent_loop.py -q && .venv/bin/ruff check src tests && .venv/bin/mypy src`

Commit: `feat(yurutme): buyuyen gorevi otomatik workflowa yukselt`

### Task 4: Tipli plan, DAG ve kanıt modeli

**Files:**
- Create: `src/fusion_cli/core/execution_plan.py`
- Create: `src/fusion_cli/engines/agent/plan_parser.py`
- Create: `src/fusion_cli/engines/agent/prompts/execution_plan.md`
- Test: `tests/test_execution_plan.py`
- Test: `tests/test_plan_parser.py`

**Interfaces:**
- Produces: `PlanStatus`, `StepStatus`, `RetrySafety`
- Produces: `ExecutionPlan`, `PlanStep`, `StepEvidence`
- Produces: `validate_plan(plan: ExecutionPlan) -> PlanValidation`
- Produces: `parse_execution_plan(text: str) -> ExecutionPlan`
- Produces: `ready_steps(plan: ExecutionPlan) -> tuple[PlanStep, ...]`

- [ ] **Step 1: Geçerli plan, boş hedef, duplicate kimlik, bilinmeyen bağımlılık ve cycle testlerini yaz**

```python
def test_plan_dongusel_bagimliligi_reddeder():
    plan = make_plan(step("a", depends_on=("b",)), step("b", depends_on=("a",)))
    result = validate_plan(plan)
    assert result.ok is False
    assert result.errors == ("Plan bağımlılık döngüsü içeriyor: a → b → a",)
```

- [ ] **Step 2: RED çalıştır**

Run: `.venv/bin/pytest tests/test_execution_plan.py tests/test_plan_parser.py -q`

- [ ] **Step 3: Frozen modelleri, JSON ayrıştırmayı ve deterministik DAG doğrulamayı uygula**

- [ ] **Step 4: Test, Ruff ve mypy çalıştır**

- [ ] **Step 5: Commit et**

Commit: `feat(plan): dogrulanabilir gorev plani ekle`

### Task 5: Plan üretimi ve mevcut agent üzerinden adım yürütme

**Files:**
- Create: `src/fusion_cli/engines/agent/plan_runner.py`
- Modify: `src/fusion_cli/engines/agent/playbook_stage.py`
- Modify: `src/fusion_cli/engines/agent/loop.py`
- Test: `tests/test_plan_runner.py`
- Test: `tests/test_agent_loop.py`

**Interfaces:**
- Produces: `PlanGenerator` protokolü
- Produces: `StepExecutor` protokolü
- Produces: `run_execution_plan(task, deps, run_agent, *, promotion=None) -> AgentOutcome`
- Consumes: `run_agent(task, deps, depth=1, self_review=False)`

- [ ] **Step 1: Planın sırayla yürütüldüğünü ve bağımlılık kanıtlarının alt tura aktarıldığını test et**

```python
async def test_runner_bagimli_adimlari_sirayla_calistirir():
    plan = make_plan(step("inspect"), step("patch", depends_on=("inspect",)))
    result = await run_with_fake_agent(plan)
    assert result.executed_step_ids == ("inspect", "patch")
    assert "inspect" in result.prompts[1]
```

- [ ] **Step 2: RED çalıştır**

- [ ] **Step 3: Mevcut workflow girişini yeni runner'a bağla; eski sabit aşamaları uyumluluk adaptörüne indir**

- [ ] **Step 4: Geçersiz plan için yalnız bir onarım turu ve uydurma ilerleme üretmeyen sonuç ekle**

- [ ] **Step 5: İlgili kapıları çalıştır ve commit et**

Run: `.venv/bin/pytest tests/test_plan_runner.py tests/test_agent_loop.py tests/test_workflow.py -q && .venv/bin/ruff check src tests && .venv/bin/mypy src`

Commit: `feat(agent): plan adimlarini temiz alt turlarda yurut`

### Task 6: Adım kanıtı ve iki seviyeli doğrulama

**Files:**
- Create: `src/fusion_cli/engines/agent/step_verification.py`
- Modify: `src/fusion_cli/engines/agent/plan_runner.py`
- Modify: `src/fusion_cli/engines/agent/verification.py`
- Test: `tests/test_step_verification.py`
- Test: `tests/test_plan_runner.py`

**Interfaces:**
- Produces: `StepVerificationResult(ok, evidence, findings)`
- Produces: `verify_step(step, outcome, deps) -> StepVerificationResult`
- Produces: `verify_plan_acceptance(plan, deps) -> VerificationResult`

- [ ] **Step 1: `outcome.ok=True` olsa bile başarısız post-condition'ın adımı düşürdüğünü test et**

```python
async def test_arac_basari_dese_bile_post_condition_adimi_basarisiz_yapar():
    result = await verify_step(file_step("main.tscn"), successful_outcome(), deps_with_missing_file())
    assert result.ok is False
    assert "beklenen dosya bulunamadı" in result.findings
```

- [ ] **Step 2: RED çalıştır**

- [ ] **Step 3: Changeset, araç sonuçları ve mevcut verifier'lardan tipli kanıt üret**

- [ ] **Step 4: Final kabul doğrulamasını runner bitişine bağla**

- [ ] **Step 5: Testleri ve kalite kapısını çalıştır; commit et**

Commit: `feat(dogrulama): plan adimlarini ve final sonucu kanitla`

### Task 7: Hata sınıflandırma ve güvenli kurtarma

**Files:**
- Create: `src/fusion_cli/core/failure.py`
- Create: `src/fusion_cli/engines/agent/recovery.py`
- Modify: `src/fusion_cli/engines/agent/plan_runner.py`
- Test: `tests/test_recovery.py`
- Test: `tests/test_plan_runner.py`

**Interfaces:**
- Produces: `FailureCategory`, `RecoveryAction`, `FailureRecord`
- Produces: `classify_failure(outcome, verification) -> FailureRecord`
- Produces: `choose_recovery(failure, step, attempts) -> RecoveryDecision`

- [ ] **Step 1: Her hata sınıfı ve yıkıcı retry yasağı için test yaz**

```python
def test_yikici_adim_otomatik_tekrar_almaz():
    decision = choose_recovery(timeout_failure(), destructive_step(), attempts=1)
    assert decision.action is RecoveryAction.PAUSE
```

- [ ] **Step 2: RED çalıştır**

- [ ] **Step 3: Saf sınıflandırma ve karar matrisini uygula**

- [ ] **Step 4: Farklı argüman, geçici geri çekilme, dış durum gözlemi ve plan onarımını runner'a bağla**

- [ ] **Step 5: Kapıları çalıştır ve commit et**

Commit: `feat(agent): hataya gore guvenli kurtarma ekle`

### Task 8: Checkpoint ve doğrulanmış devam

**Files:**
- Create: `src/fusion_cli/core/checkpoint.py`
- Create: `src/fusion_cli/memory/checkpoint_store.py`
- Modify: `src/fusion_cli/engines/agent/plan_runner.py`
- Modify: `src/fusion_cli/engines/agent/loop.py`
- Test: `tests/test_checkpoint_store.py`
- Test: `tests/test_plan_resume.py`

**Interfaces:**
- Produces: `WorkflowCheckpoint`, `CheckpointStore` protokolü
- Produces: `JsonCheckpointStore(base_dir: Path)`
- Produces: `save(checkpoint)`, `load(plan_id)`, `find_resumable(root, conversation_id)`

- [ ] **Step 1: Atomik round-trip, bozuk kayıt ve sır/prompt saklamama testlerini yaz**

- [ ] **Step 2: RED çalıştır**

- [ ] **Step 3: Geçici dosya + `os.replace` kullanan JSON adaptörünü uygula**

- [ ] **Step 4: Devam sırasında tamamlanan adımın post-condition'ını yeniden denetle; yalnız geçerli adımları atla**

- [ ] **Step 5: Kesinti entegrasyon testini çalıştır ve commit et**

Commit: `feat(bellek): workflow checkpoint ve devam destegi ekle`

### Task 9: Bütçe zarfları ve duraklatma

**Files:**
- Modify: `src/fusion_cli/engines/workflow/model.py`
- Modify: `src/fusion_cli/engines/agent/plan_runner.py`
- Modify: `src/fusion_cli/config/models.py`
- Modify: `src/fusion_cli/config/defaults.yaml`
- Test: `tests/test_workflow_budget.py`
- Test: `tests/test_plan_runner.py`

**Interfaces:**
- Produces: `WorkflowBudget(planning, per_step, recovery, final_verification)`
- Produces: `BudgetLedger.charge(envelope, calls) -> BudgetDecision`

- [ ] **Step 1: Zarfların bağımsız tükenmesi ve checkpoint'li pause testlerini yaz**

- [ ] **Step 2: RED çalıştır**

- [ ] **Step 3: Gerçek model/araç sayaçlarından beslenen ledger'ı uygula**

- [ ] **Step 4: Magic number bırakmadan config varsayılanlarını ekle ve eşleşme testi yaz**

- [ ] **Step 5: Kapıları çalıştır ve commit et**

Commit: `feat(butce): workflow cagrilarini ayri zarflarda izle`

### Task 10: Workflow olayları ve UI görünürlüğü

**Files:**
- Modify: `src/fusion_cli/core/events.py`
- Modify: `src/fusion_cli/engines/agent/plan_runner.py`
- Modify: `src/fusion_cli/ui/renderer.py`
- Modify: `app/src/protocol/olayAkisi.ts`
- Modify: `app/src/protocol/olayMetni.ts`
- Modify: `app/src/screens/Conversation.tsx`
- Modify: `app/src/screens/Conversation.css`
- Test: `tests/test_renderer.py`
- Test: `tests/test_plan_runner.py`
- Test: `app/src/protocol/olayAkisi.test.ts`
- Test: `app/src/protocol/olayMetni.test.ts`
- Test: `app/src/screens/Conversation.test.tsx`

**Interfaces:**
- Produces: rota, yükseltme, plan, adım, doğrulama, retry, checkpoint, pause ve completion olayları

- [ ] **Step 1: Python olay sırası ve renderer metni için kırılan testleri yaz**

- [ ] **Step 2: `olayAkisi`, `olayMetni` ve `Conversation` için masaüstü olay/görünüm testlerini yaz**

- [ ] **Step 3: RED Python ve frontend testlerini çalıştır**

- [ ] **Step 4: Tipli olayları yayınla; UI'da plan ve kanıt ilerlemesini göster**

- [ ] **Step 5: Basit görevde plan görünmediğini test et**

- [ ] **Step 6: Python, frontend, Ruff, mypy ve build kapılarını çalıştır; commit et**

Commit: `feat(ui): profesyonel workflow ilerlemesini goster`

### Task 11: Çok alanlı davranış değerlendirmesi

**Files:**
- Create: `evals/professional_execution.py`
- Create: `tests/test_professional_execution_eval.py`
- Modify: `tests/test_evals.py`
- Modify: `docs/EXECUTION_PROFILES.md`

**Interfaces:**
- Produces: `ProfessionalExecutionMetrics(acceptance_ok, false_successes, blind_retries, repeated_completed_steps, model_calls, tool_calls, elapsed_s)`

- [ ] **Step 1: Tur tamamlandı fakat kabul koşulu başarısız senaryonun metriğini test et**

- [ ] **Step 2: RED çalıştır**

- [ ] **Step 3: Ağsız sahte araçlarla basit, çok dosyalı, hata onarımlı, MCP ve kesinti senaryolarını uygula**

- [ ] **Step 4: Mevcut Godot ölçüm sürücüsünü değiştirmeden yeni metrik biçimine adaptör ekle**

- [ ] **Step 5: Tam kalite kapısını çalıştır ve commit et**

Run: `.venv/bin/ruff check . && .venv/bin/mypy src && .venv/bin/python -m pytest -q`

Commit: `test(eval): profesyonel yurutmeyi cok alanda olc`

### Task 12: Güncel runtime, macOS paket ve kurulu uygulama kabulü

**Files:**
- Generated: `app/src-tauri/resources/runtime/runtime-manifest.json`
- Generated: `app/src-tauri/resources/runtime/fusion-runtime.tar.gz`
- Generated: `app/src-tauri/target/release/bundle/macos/Fusion.app`
- Generated: `app/src-tauri/target/release/bundle/dmg/*.dmg`
- Test: `desktop_build/macos/smoke_app_bundle.py`

**Interfaces:**
- Consumes: Güncel git HEAD ve bütün kaynak/test değişiklikleri
- Produces: Hash doğrulanmış `Fusion.app`, DMG ve `/Applications/Fusion.app` kurulumu

- [ ] **Step 1: Kaynakta tam kalite kapısını yeniden çalıştır**

Run: `.venv/bin/ruff check . && .venv/bin/mypy src && .venv/bin/python -m pytest -q`

- [ ] **Step 2: Frontend test ve production build çalıştır**

Run: `cd app && npm test -- --run && npm run build`

- [ ] **Step 3: Güncel runtime ve macOS paketini üret**

Run: `cd app && npm run bundle:mac`

- [ ] **Step 4: Paket smoke ve imza doğrulamasını çalıştır**

Run: `.venv/bin/python desktop_build/macos/smoke_app_bundle.py app/src-tauri/target/release/bundle/macos/Fusion.app`

- [ ] **Step 5: Üretilen uygulamayı `/Applications/Fusion.app` üzerine güvenli paketleme akışıyla kur**

- [ ] **Step 6: Kurulu ve üretilen runtime hash'lerini birebir karşılaştır**

```bash
shasum -a 256 /Applications/Fusion.app/Contents/Resources/runtime/fusion-runtime.tar.gz app/src-tauri/target/release/bundle/macos/Fusion.app/Contents/Resources/runtime/fusion-runtime.tar.gz
```

- [ ] **Step 7: Kurulu uygulamada basit hızlı görev ve karmaşık otomatik workflow kabul koşularını çalıştır**

- [ ] **Step 8: Artakalan süreç, başarısız test ve paket farkı olmadığını doğrula; sonuç raporunu yaz**

- [ ] **Step 9: Üretim kaynağı ve raporu commit et; generated build dizinini commit etme**

Commit: `chore(macos): guncel profesyonel yurutme paketini dogrula`

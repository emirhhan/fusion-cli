# Fusion profesyonel kullanım Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fusion'ın masaüstü, CLI ve Kits yüzeylerinde doğru model, izin, soru, iş durumu ve teslim kanıtıyla güvenilir günlük çalışma sağlaması.

**Architecture:** Mevcut tipli core olayları, ApprovalPolicy, ModelCapability, provider adapter'ları, checkpoint ve tool registry otorite olarak korunur. UI'lar bu verinin uyumlu projection'larını kullanır; ikinci agent loop/model yöneticisi/scheduler yazılmaz. Ana App ve Kits ayrı build/runtime sınırında kalır, sürümlü host sözleşmeleriyle birleşir.

**Tech Stack:** Python 3.11 venv; React/TypeScript/Tauri; App CI Node22; Kits scriptleri Node24.21.0; Vitest/Playwright/pytest; mevcut MCP SDK ve provider adapter'ları.

**Spec:** `docs/superpowers/reports/2026-10-12-fusion-profesyonel-arastirma/README.md` ve 01–07 ekleri. `07-kaynak-ve-karar-defteri.md` D01–D05 normatif öneri sözleşmesidir; belirsizlikte bu kararlar esas alınır. Ana raportaki ürün sözleşmeleri normatiftir. U/E/K/R katalogları öneri kapsamını tanımlar. Buradaki paketler uygulama sırasıdır; bir paketteki ilk test başarısızlığı görülmeden üretim düzeltmesi yazılmaz.

## Global Constraints

- Mevcut branch ve kullanıcı değişiklikleri korunur; push/merge/yeni branch talimatı yok.
- Repo `.env` ve secret içerikleri okunmaz, rapora/teste/log'a yazılmaz.
- Ücretsiz kullanım yolu korunur. GPT-6.1 Sol low uygulayıcı tercihi, Fusion varsayılan modeli değildir.
- Türkçe kullanıcı metinleri/docstring/log; mevcut katman sınırları; core stdlib; typed frozen dataclass.
- CLI/Desktop/Kits'te aynı izin ve sonuç otoritesi. Zaman aşımı ve kapanma onay değildir.
- Değiştirici işin tekrarında external idempotency kanıtı yoksa otomatik retry yok; önce observation.
- Eski protokolü kıran değişiklikler migration ve compatibility test olmadan uygulanmaz.
- App ve Kits runtime'ları ayrıdır. Global Node26 test sonucu desteklenen Node sonucu diye sunulmaz.
- Ağır pytest ve `evals.kabul` paralel koşturulmaz. Kullanıcı web profiline ağır otomasyon testleri uygulanmaz.
- Tam kalite kapısı geçmeden kod commit yok; conventional Türkçe commit, author/co-author ekleme yok.
- Kullanıcı 12 Ekim'de 16 paketin bu oturumda uygulanmasını istedi. Paketler ayrı kapsam, doğrulama ve ilerleme kaydıyla sıralı uygulanır.

## Review Focus

1. Geç gelen cevap/model seçimi/olay başka tur veya sohbetin state'ini değiştirmemeli: paket 2/4/5.
2. UI kapanırken taslak, belge ve tamamlanmış artefakt kaybolmamalı: paket 2/3/8/11.
3. RequestId tekrarında dış mutasyon ikinci kez yapılmamalı: paket 2/5/8.
4. Sağlayıcı yeteneği bilinmiyorsa model adı veya UI seçimi kanıt yerine geçmemeli: paket 4/10.
5. Eski çekirdek/istemci additive alanı tolere etmeli; yeni kritik eylemi yanlış başarıya çevirmemeli: paket 2/12.

## Ön kontrol ve yürütme yöntemi

Katalogdaki “kaynakta eksik” her maddede önce güncel revision'ı oku. Başka hesap uygulamaya başladığında dosyalar değişmiş olabilir. İlgili davranış artık doğruysa yeniden yazma; test/kanıtla “zaten mevcut” işaretle. Line number'lara kör güvenme, sembol adına git.

Paket başına kapsamlı plan büyütmek yerine burada verilen imza/test/alanları kullan. İsimler **önerilen yeni interface** ise aşağıda belirtilir; mevcut API olduğu varsayılmaz. Yeni tip eklenecekse mevcut eşdeğer tip olup olmadığını önce ara.

Çalışma ağacı şu an menü/oyun kanıtı değişiklikleri ve iki önceki belge içeriyor. Araştırma dosyaları bunların üstüne ekleniyor. `git add .` yerine paket dosyalarını seç. `node_modules/` ekleme.

### Ortak doğrulama komutları

Fusion CLI kökünde:

```sh
.venv/bin/pytest -q tests/ILGILI_DOSYA.py
.venv/bin/ruff check .
.venv/bin/ruff format --check src tests evals prompt_opt desktop_build
.venv/bin/mypy
.venv/bin/pytest -q
git diff --check
```

`ILGILI_DOSYA.py` gerçek paket testine değiştirilir; placeholder komut koşturulmaz. Tam format `.` tarihi Markdown codeblock'larında yedi eski farklılık bulmuştu; ürün kod kapısını geçmek için unrelated tarihî belgeleri yeniden formatlama. Format kapsamı ve nedeni kapı kaydında açık yazılır.

App kökünde:

```sh
PATH=/opt/homebrew/opt/node@22/bin:$PATH npm test -- --maxWorkers=1
PATH=/opt/homebrew/opt/node@22/bin:$PATH npm run build
```

Bu Node yolu bu Mac'e ait; başka Mac'te Node22 executable bulunup aynı version check yapılır. Kits kökünde package.json `kits:check` Node24.21.0 hattını kullanır. Önce scripti oku; canlı model/haricî servis çağıran smoke'ları unit kapısı diye koşturma. `npm run typecheck`, ilgili Vitest ve mevcut build/lint/format scriptleri ayrı kontrol edilir. Tauri/Rust değiştiğinde App `check:ci` ve platform smoke gerekir; yalnız Markdown değiştiğinde ürün kapısını tekrar çalıştırma.

## Paket 1 — Kırmızı tabanı teşhis et ve runtime'ı görünür kıl

**Kapsam:** README başlangıç tablosundaki üç pytest başarısızlığı + R33. **Dosyalar:** `tests/test_kabul_html_game.py`, `tests/test_remotion_kit.py`, `tests/test_remotion_observe.py` ve teşhisin gösterdiği mevcut ürün modülü; App/Kits runtime scriptleri gerekiyorsa. **Ürettiği:** doğru temel kapı kaydı; diğer paketler bunu tüketir.

- [x] Üç testi tek başına, sıralı koştur; eski tüm koşuyla aynı/assertion farklı mı kaydet.
- [x] Root cause için browser/render hazır olma sinyali, süreç başlangıcı ve state hook sonucunu incele. Sabit sleep uzatarak assertion gevşetme.
- [x] Ürün kusuruysa gerçek regresyon; test senkronizasyonuysa event/barrier temelli regresyon yaz. Yeni testi fail gör.
- [x] Yalnız sorumlu kodu düzelt; Node22/App ve Node24/Kits ayrımını script/doctor'da belirginleştir. Runtime resolver eklenirse signature `resolve_runtime(project_kind, installed_versions)` saf karar olarak mevcut config katmanında tutulur; shell komut metnine secret ekleme.
- [x] İlgili üç test; lint/type; gerekli tam Python kapısı; değiştiyse App/Kits kontrolü. Sonucu devam dosyasına yaz ve temizse yalnız ilgili paketi commit et.

## Paket 2 — Olay, mesaj ve gönderim kimliği

**Kapsam:** U11/U17/U24, K02/K04, R07/R08. **Dosyalar:** `core/events.py`, `appserver/protocol.py`, `appserver/session.py`, App protocol/types, sessions/types/useSessions, Composer; Kits Chat/local-threads/Fusion event adapter. **Önerilen yeni interface:** `SubmissionReceipt { requestId: string; sessionId: string; turnId: string | null; state: 'queued'|'accepted'|'running'|'failed'|'cancelled'; error: string | null }`. TS yalnız UI adapter'da bu biçime normalize eder; wire Türkçe isimlerini korur. `onSend` void yerine receipt/promise kabulü tasarlanır; eski callback uyumu tek adapter'da.

- [x] A04/A05/A06/A34 için fake transport testleri yaz: send reject taslağı korur; iki Enter tek accepted; stale event başka sohbete gitmez; duplicate replay çoğaltmaz.
- [x] Testleri kırmızı gör. Mevcut client request id ve backend request id'yi yeni paralel UUID sistemi kurmadan genişlet.
- [x] D01 durable backend dedup ve task-attempt yaşam döngüsünü uygula. Backend accepted makbuzunu gerçek task kabulünde üret; failed teslimde taslak/ek snapshot'ını retry için tut. Mesajın kalıcı id'si React key olur; eski geçmiş için deterministik migration id üretilir.
- [x] UI reducer duplicate event'i ayıklar; tur tamamlandı event'i tek kez. Bilinmeyen optional alan tolere, bilinmeyen critical action unsupported döner.
- [x] Unit/protocol testleri + full gates; integration transcript örneğiyle yeni ve eski istemciyi doğrula. Commit sonrası receipt interface'ini devam dosyasına yaz.

## Paket 3 — Karşılama ve async UI doğruluğu

**Kapsam:** U01–U10/U19/U21/U31/U32, K27. **Dosyalar:** `App.tsx`, `SessionApplication.tsx::ConnectedOnboarding`, onboarding, Settings, ImageCreate. **Önerilen yeni ortak interface:** `AsyncState<T> = {status:'loading'} | {status:'ready';value:T} | {status:'error';message:string}`; “boş” ready value'dur. Genel state store yazılmaz; ekran adapter'ında kullanılır.

- [x] A01/A02/A03/A28: localStorage throw, bağımsız keşif fail, count unknown, provider configured-but-unverified ve image load error fixture.
- [x] Mutasyon sonucu `{ok:false}` ile promise reject ayrı tests; her ikisinde görünür hata ve önceki state. Kırmızı testleri gör.
- [x] `Promise.allSettled` veya eşdeğer bağımsız sonuç işle; doğrulanmamış apprentice active false demek yerine pending/unknown olsun; kaynak sayısı yoksa “Bulundu”.
- [x] Projesiz devam ve kurulum restore; güvenli storage adapter; reset/load/save için pending ve retry. Kopyalama başarılı/başarısız makbuzu.
- [x] İlgili Vitest + visual mevcut fixture'ı güncel karar ile kıyasla; test/build. Native ilk açılış kabulü daha sonra paket16'da.

## Paket 4 — Model ve thinking sözleşmesi

**Kapsam:** U18/U26–U30, E33, R01–R06. **Dosyalar:** `core/model_capability.py`, `core/types.py`, `appserver/model_catalog.py`, provider capabilities, config, ModelPicker/Models/Composer, protocol; Kits model adapter.

**Önerilen additive interface:** mevcut ModelCapability'ye `supported_reasoning_efforts: tuple[str,...] = ()`, `reasoning_efforts_verified: bool = False`. Boş verified=false bilinmiyor; boş verified=true desteklenmiyor. UI `requestedModel`, `observedModel: string|null`, `fallbackReason:string|null` metadata'sını mevcut olaylardan alır. Sağlayıcı bu effort listesini gerçekten bildirmiyorsa doküman/ölçüm kaynağı ayrı kaydedilir; model adından tahmin yok.

- [ ] A12–A16: stale model selection, rejected selection, fallback, unknown observed, unsupported effort ve mutation eligibility.
- [ ] Kırmızı testleri gör; API adapter contract ve web/template kontrolünü ayır. GPT-6.1 Sol adapter seçilirse resmî Responses tool contract; Fusion defaults değiştirilmez.
- [ ] Model katalogu typed capability projection üretir; UI arama, klavye, loading/error/retry, bağlan eylemi. Çalışan turda model bilgisi görünür, değişiklik sonraki turda.
- [ ] Thinking gösterim ayarı gerçek effort'u değiştirmez; template disable toggle yalnız destekleyen adapter'a gider.
- [ ] Capability/model/approval testleri, UI test/build, full Python. Gemini requested/observed örneği gerçek smoke ile doğrulanır; yedek modeli primary başarı gibi raporlama.

## Paket 5 — İşlem onayı ve soru yaşam döngüsü

**Kapsam:** U33–U35, E15–E22, R09/R15/R32. **Dosyalar:** `engines/agent/approval.py`, engine_tools/loop/clarify, appserver question/approval summary, App Approval/types, voice answer bridge. **Tüketir:** paket2 session/turn/request ids; D03 aktif göreve steer / açık bağımsız queue kararı.

**Önerilen interface:** mevcut SessionQuestion kimliği kullanılır; yanıt envelope'una `questionId`, `turnId` ve `decisionId` korelasyonu eklenir. `decision` izin için once/session/deny; bilgi için text/choice; timeout/cancel ayrı terminal. Existing protocol kelimeleri migration adapter'da korunur. AuthorizationScope sunucu/hesap/eylem/normalize hedef parmak izi tutar; raw secret içermez.

- [ ] A08–A11/A32: ardışık soru state reset, double send, stale ses cevabı, target değişikliği, policy revoke, Escape deny olmayan kart.
- [ ] Fail test; parent request kapsamını callback/key ile doğrula. Timeout önerilen seçeneği yanıt yapmaz.
- [ ] ApprovalMemory'yi mevcut shell scope'u bozmadan uzak hedef kapsamıyla genişlet; kullanıcı geniş izin seçiyorsa scope açık metinle göster. Deny/blocked/optional default ayrı.
- [ ] Kart pending iken disabled; gönderim fail ise retry; kapanışta odak geri. Async optional soru bağımsız işi durdurmaz; required dependent iş bekler.
- [ ] Approval/loop/voice ve UI testler; güvenli fixture dış etki tekliği; full gate. Onay politikası değişikliği görünür release notu.

## Paket 6 — MCP dayanıklılığı ve bağlantı merkezi

**Kapsam:** E01–E08, R17/R18/R19. **Dosyalar:** mcp_bridge tool_effect/client/pool/service/oauth/tokens, config trust metadata, connectors/control.

- [ ] A17–A19: annotation conflict, trusted/untrusted read, asılı list/call, refresh yarış, close cancel. Kırmızı testleri gör.
- [ ] Fusion için çelişkide destructive/unknown kararı uygula; bunun daha ihtiyatlı ürün politikası olduğunu dokümante et. Var olan Codex read-first davranışı standardı ihlal ediyor diye iddia etme.
- [ ] D02 yeni sunucuda unreviewed trust ve legacy explicit scope migration uygula. Server bazlı connect/list/call/close bütçesi ve bounded backoff; token single-flight, typed health/provenance metadata; sır loglama yok.
- [ ] UI bağlandı/parked/degraded/auth gerekli ayrımı ve retry. Bir sunucu fail tüm listeyi boşaltmaz.
- [ ] Yerel STDIO+HTTP fixture connect/list/read/cancel/close smoke; unit/full gate. **Yeni MCP sürüm geçişi bu pakette bütün eski handshake'i silmez.** Ayrı protocol matrix işi paket15'tedir.

## Paket 7 — Ajan ekipleri ve skill doğruluğu

**Kapsam:** E09–E14/E23–E26, R19–R21. R22/R23 bu paketin zorunlu kapsamına dahil değil; P2 ayrı teslim. **Dosyalar:** team, capabilities/expertise, existing subagent card/UI and MemoryPanel. **Ürettiği:** scope-normalized child result ve skill origin evidence.

- [ ] A20/A21: alias/symlink scope çakışması, child parent dışına çıkış, bir child exception ve bütçe. Skill collision/unknown tool/hash değişimi testleri.
- [ ] Fail test; root kanonik çözümlerini mevcut path validator üzerinden birleştir; child yalnız parent kapsamını daraltır.
- [ ] Child terminal sonucu exception/cancel durumunda da bir kez; independent sibling korunur, parent cancel hepsini durdurur. Çağrı/doğrulama/süre bütçesi mevcut TurnBudget otoritesine bağlı. Token sayacı henüz yok; provider usage destekli additive sayaç ayrı E12 alt işi. Usage bilinmiyorsa kesin token tavanı garantisi verilmez.
- [ ] Skill katalogunda origin/version, explicit/implicit loading receipt. Remote allowed-tools grant sayılmaz. Tek yüksek güvenli skill otomatik ipucu yaklaşımı korunur.
- [ ] team/capability unit+full gate; UI team fixture. R22/R23 öğretmen açıklaması ve ders invalidation bu pakette uygulanmaz; P2 ayrı küçük görev olarak planlanır.

## Paket 8 — Checkpoint, devam ve gerçek iptal

**Kapsam:** E27–E32, R10/R14. **Dosyalar:** checkpoint_store, core/checkpoint, plan_checkpoint/recovery/liveness, tools/jobs, appserver cancellation. **Tüketir:** paket2/5 kimlik ve izin sonucu.

- [ ] A22–A24: same-job polling, iki plan adı collision, aynı PID parallel save, crash before replace, stale revision, v999, external executed-response-lost.
- [ ] Fail test; unique temp+atomic replace, durability yalnız platformda desteklenen fsync; revision karşılaştırması lock/protokol ile korunur. Eski path migration read gerekir.
- [ ] Resume completed effect'i yeniden çalıştırmadan observation; kaynak değişimi dependent step invalidation. Ham source/prompt checkpoint'e ekleme.
- [ ] Stop gerçek owned process/task temizliğini bekler ve sonucunu UI'ya yollar; bağımsız başka session'a dokunmaz.
- [ ] Checkpoint/recovery/jobs unit+subprocess fixture; full gate; crash/reopen gerçek native smoke paket16'da.

## Paket 9 — Kanıtlı kapanış ve çalışma akışı

**Kapsam:** R11–R16/R24, U22/U23/U25, E35. **Dosyalar:** core artifacts/events, existing turn/completion report, Conversation/ActivityLine/PreviewPanel/ChangesPanel; no new agent engine.

- [ ] Wrong-success, NoFileChanges, partial, stale screenshot, duplicate final, future schema ve rejected candidate transcript testleri.
- [ ] Fail test; mevcut runtime `TurnOutcome` ve verifier otoritesiyle teslim kartı. Modelin “bitti” metni status değiştirmez.
- [ ] Teslimde dosya/URL açma, screenshot viewport, source, verification receipt; yukarı okuyan kullanıcı scroll korunur, yeni mesaj düğmesi.
- [ ] Uzun geçmiş performansı ölçülür; mevcut perf test karşılaştırılır. Gerekliyse bounded render; erişilebilirliği bozan kör virtualization yok.
- [ ] Completion/unit/UI+visual/full gates. E35 loop modülerleştirme davranış snapshot'ıyla ayrı alt değişiklik; yeni özellik refactor'a karıştırılmaz.

## Paket 10 — Görsel üretim iş protokolü

**Kapsam:** K27–K35, R26/R27/R29. **Dosyalar:** appserver/image_create/image_flows, providers/image_generation/web_image/nim_image, ImageCreate/akis/akisCalistir/AkisTuvali.

**Önerilen interface:** `ImageJobReceipt {jobId:string; state:'queued'|'running'|'partial'|'completed'|'failed'|'cancelled'; assetIds:string[]; error:string|null}`. Gerçek dosya teslimi current image core üzerinden; yeni provider implementasyonu gerekmez. RPC jobId/cancel existing tools/jobs ile eşdeğer ise onu kullan. Cancellation external provider'ı durduramıyorsa kesin “uzak iş iptal edildi” iddiası yok; sonraki varyasyonun başlaması engellenir.

- [ ] A28–A31: initial load error, DAG duplicate/cycle/NaN, atomic save interruption, exact_size unknown, cancel after first image, MIME fake/login HTML, missing target.
- [ ] Fail test; server-side DAG validation ve atomic flow persistence; progress/cancel task ownership, partial results retain.
- [ ] Basit üretim ve advanced flow; provider capability'ye göre oran/referans/seed. Hedef asset görünür; asset yoksa iş durur.
- [ ] Viewer focus trap/return; gallery partial badge; missing variant retry yalnız eksik varyasyona. Test/unit/full gates.
- [ ] Mevcut bağlı sağlayıcıyla dar gerçek generate/edit smoke; dosya açılır, dimensions/alpha ve referans gözle kıyaslanır. Model metni dosya kanıtı değildir.

## Paket 11 — Kits sohbet ve belge dayanıklılığı

**Kapsam:** K01–K17/K23/K25, R30/R31. **Dosyalar Kits:** ThreadList, Chat, SpaceWorkspace/SpaceLibrary/PageDocument/PageReviewCard, editor autosave, api, local-threads/page-service/local-computer-bridge. **Tüketir:** paket2 task receipt; paket5 question; varsa mevcut host bridge adapter.

- [ ] A25–A27: remote-only page2 thread, delayed poll, area switch, double create, draft restart, stale expectedRevision, agent patch conflict.
- [ ] Fail test; real merged pagination, scoped async load with AbortSignal, pending create, Turkish search.
- [ ] Draft persistent key conversation/page+revision; storage failure visible; successful save retires only matching draft. Conflict diff/merge explicit.
- [ ] Host calls cancelled on teardown; keyboard Tabs. Büyük library için önce5.000 ölçüm, gerekliyse sunucu paginated search; 10.000 galeri ayrı paket12.
- [ ] Kits type/lint/unit/build/format ve gerçek host integration smoke. Node22 kullanma; Kits kendi pinned scriptini kullan. Main App code değişmediyse bütün Rust build'i burada tekrar etme.

## Paket 12 — Ortak artefakt köprüsü ve birleşik tasarım

**Kapsam:** K26/K32/K33, R25/R28/R35. **Dosyalar:** core/artifacts, appserver image/library, App library/preview/ui/theme; Kits host api/editor/generated theme scripts. **Önerilen additive interface:** mevcut artefakt tipine `asset_id`, `kind`, `mime`, `relative_path`, `created_by_task_id`, `parent_asset_ids`, `metadata_version`. Boyut/alpha/model/seed yalnız biliniyorsa alan; yoksa null/unknown. Host resolver projenin allowlist kökleriyle path çözümlemeli.

- [ ] Aynı asset chat/gallery/page roundtrip; migration eski path; root escape; missing file; parent deleted; unknown metadata; A34 backward host testleri.
- [ ] Fail test; tek artefact authority; mevcut gallery sidecar ile migration. Galeri index/pagination total order; gerektiğinde corruption recovery scan.
- [ ] Ortak token'lar tek kaynaktan üretilir; shared davranış şartnamesi App/Kits adapter'a taşınır. React major'larını aynı pakete zorla birleştirme.
- [ ] Yeni image comments/compare ayrı küçük UI alt görevi; mask edit unsupported capability açık. Unit/browser/visual; iki repo gate; packaged bridge smoke.

## Paket 13 — Ses ve tarayıcı gerçek kabulü

**Kapsam:** K18–K22/K24/K25, R05/R32. **Dosyalar:** main voice ask/answer, Kits local voice/CallView, web login/browser host, computer panel.

- [ ] A32 + mikrofon reddi, speaker unavailable, TTS fail, hangup pending, same profile lock, visible window false-positive fixtures.
- [ ] Fail test; task/question correlation, owned cancel; TTS fail text preserved; buffer/receipt idempotency.
- [ ] Kullanıcı cihazında native visible login, mikrofon giriş, local STT/TTS ve browser devralma. Şifre/çerez okunmaz. Açılan pencere ekranda doğrulanmadan “açtım” başarı metni yok.
- [ ] Unit/full relevant gates + L12 kanıt. Kullanıcının cihaz adımı gereken yerde gerçek blocker olarak açık söylenir; diğer bağımsız işler sürdürülür.

## Paket 14 — Günlük işler ve üretim kalitesi

**Kapsam:** L02–L11, R24/R37/R38. **Dosyalar:** existing `evals/suite/production.yaml`, `evals/kabul`, skills and actual product tool/engine paths where evidence points.

- [ ] Aynı brief/input/provider/izin ile taban kaydı; günlük araştırma, kod düzeltme, MCP taslak ve belge senaryoları.
- [ ] Site/game/video işler sıralı boş output kökünden Fusion üretimi. Başarısız output'u root elle düzeltip Fusion başarısı sayma.
- [ ] Ürün kusuruna source regresyon; kabul ölçerindeki kusursa evaluator düzeltmesi ayrı. İkisini parite kanıtı diye birleştirme.
- [ ] Gerçek viewport/kare/etkileşim+insan rubriği. Başarısız denemeler ve unavailable ayrı ama saklanmaz.
- [ ] Kalite kapısı ve tekrar aynı kabul. “ChatGPT yerine kullanım” kararı başarısızlık/data-loss/false success matrisiyle verilir; yüzde uydurma.

## Paket 15 — Protokol/dağıtım olgunluğu ve ileri fikirler

**Kapsam:** MCP2026 migration matrix, R34/R36/R39/R40/E34. P2 işlerin hepsi zorunlu ilk yayın değil.

- [ ] Mevcut Python/TS MCP SDK sürümünü lock'tan doğrula; legacy ve yeni stateless adapter için ayrı fixture. Legacy initialize/initialized akışını korur. Yeni 2026-07-28 adapter initialize veya Mcp-Session-Id göndermez; MCP-Protocol-Version, Mcp-Method/Mcp-Name ve _meta taşır; isteğe bağlı server/discover ayrı sınanır. SDK sürümü desteklemiyorsa sürüm-gated experimental adapter/migration gerekir; mevcut istemciye unsupported alan zorla eklenmez.
- [ ] Kaynak/time/observed başarı ve fiyat unknown dataset; routing benchmark. Cost proxy'den gerçek cost'a geçiş tek başına gratuitous default model değişimi yapmaz.
- [ ] Diagnostics export sentinel; recurring restart/delivery duplicate; recorded skill sanitize. Her biri bağımsız küçük paket olarak uygulanır.
- [ ] Yalnız ilgili kapılar ve genişlenen senaryolar. İleri liste kapıları başarısızsa mevcut günlük sürümü kırmadan feature gate/experimental etiketi.

## Paket 16 — Günlük kullanım sürümü kabulü ve devir

**Kapsam:** L01–L12 ve tamamlanan P0/P1 paketleri. **Dosyalar:** runtime/build/install scripts, existing release reports, continuation record.

- [ ] App Node22 test/build; gerekiyorsa Rust/Tauri check:ci; Kits pinned check/build; Python full gates. Koşular kaynak baskısına göre sıralı.
- [ ] Clean user profile/install fixture ve mevcut kullanıcı upgrade; transcript/checkpoint/draft/asset migration.
- [ ] Native UI klavye/VoiceOver/dark/light/zoom; screenshots güncel. Screenshot threshold'u kusuru gizlemek için artırma.
- [ ] Release manifest: commitler, bundled core+Kits sürümleri, model/connector support, test/acceptance kanıtı, bilinen eksikler, rollback yolu.
- [ ] Kullanıcı günlük üç işi Fusion'da yapar; müdahale ve hatalar ölçülür. Geçmeyen yüzeye “tam hazır” etiketi verilmez.

## Katalog kapsam haritası

U01–10→3; U11–17/24→2/5; U18/26–30→4; U19/21/31/32→3; U20→2'ye ek clipboard adapter; U22/23/25→9; U33–35→5. E01–08→6; E09–14/23–26→7; E15–22→5; E27–32→8; E33→4; E34→15; E35→9. K01–17/23/25→11; K18–22/24→13; K26→12; K27–35→10/12. R maddeleri paket başlıklarında ilişkilidir; R06/R22/R23/R36/R38/R39/R40 ileri bağımsız alt paket olarak P0/P1 sonrasında seçilir.

## Tamamlanma kaydı

Bir paketin bitti sayılması için: kapsam ID'leri, red/green test, değişen dosyalar, quality gate çıktısı, canlı kanıt gerekiyorsa yolu, inceleme sonucu, commit, açık eksik. “Tüm taskları tamamladım” doğal dil cümlesi bu kaydın yerine geçmez. Başka hesap kalan paket numarası ve önceki contract'ları `06-baska-hesaba-devret.md` üzerinden devralır.

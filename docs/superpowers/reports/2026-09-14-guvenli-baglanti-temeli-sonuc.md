# Güvenli Bağlantı Temeli — Sonuç Raporu

- **Tarih:** 2026-09-14
- **Dal:** `fusion-runtime-hardening-20260827-022831`
- **Plan:** `docs/superpowers/plans/2026-09-14-guvenli-baglanti-temeli.md`
- **Baseline referansı:** `docs/superpowers/reports/2026-09-14-platform-baseline.md` (HEAD `20a7d40`)

## Yapılanlar (commit listesi)

Bu plan boyunca eklenen commit'ler (baseline sonrası, en eskiden en yeniye):

1. `73125de` — `fix(onay): uzak araçlar auto kipte sorulmadan çalışmasın`
   `core/tools.py`'ye `ToolEffect` enum'u ve `Tool.effect` alanı eklendi;
   `engines/agent/approval.py::build_request` artık `REMOTE_WRITE` etkili araçları auto
   kipte ilk çağrıda sorup oturum boyunca hatırlıyor, `REMOTE_DESTRUCTIVE`'i her çağrıda
   `REMOTE_DESTRUCTIVE_REASON` ile soruyor, `REMOTE_READ`/`LOCAL`'i sormadan geçiriyor.
2. `59b31a7` — `feat(mcp): araç açıklamasını onay etki sınıfına çevir`
   `mcp_bridge/tool_effect.py::effect_from_annotations` MCP `ToolAnnotations`
   (`readOnlyHint`, `destructiveHint`) ipucunu yukarıdaki üç etki sınıfına çeviriyor;
   MCP istemcisi kaydettiği her araca bu etkiyi taşıyor.
3. `c0733c3` — `fix(mcp): kayıtlı ortam değişkenlerini stdio sunucusuna aktar`
   `mcp_bridge/transport.py::resolve_stdio_env` stdio alt-sürecine yalnız
   `env_names`'te açıkça listelenen değişkenleri aktarıyor. Önceden ortam SIZMIYORDU;
   tersine eksik kalıyordu: `env` verilmediği için MCP SDK sürece yalnız
   `get_default_environment()` (HOME, PATH gibi güvenli değişkenler) veriyordu ve
   bağlantı ekranında kaydedilen anahtarlar sunucuya hiç ulaşmıyordu.
4. `c5a29cd` — `refactor(mcp): eksik ortam değişkeni listesine İngilizce ad ver`
   Küçük isimlendirme düzeltmesi (aynı Görev 3 kapsamında).

Bu görev (Görev 4) yalnızca bu raporu ekliyor; kod değişikliği yok.

## Adım 1 — Tam kapılar (gerçek çıktılar)

### `.venv/bin/ruff check .`

```
All checks passed!
```

### `.venv/bin/mypy`

```
Success: no issues found in 331 source files
```

(Baseline'da 330 dosyaydı; `tool_effect.py` yeni modülüyle 331'e çıktı.)

### `.venv/bin/pytest -q --junit-xml=...`

```
$ grep -o '<testsuite [^>]*>' pytest-result.xml
<testsuite name="pytest" errors="0" failures="0" skipped="4" tests="3838" time="491.065" ...>
```

**Sonuç:** 3838 test, 3834 passed, 4 skipped, 0 failed, 0 error.

Baseline'a göre: 3816 → 3834 passed (+18), skipped sabit (4), başarısızlık yok. Artış
Görev 1-3'te eklenen `ToolEffect`/`tool_effect.py`/`resolve_stdio_env` testleriyle
uyumlu; beklenen "yalnız yeni testler kadar artış, sıfır başarısızlık" kriteri karşılanıyor.

### `(cd app && npm test)`

```
Test Files  83 passed (83)
     Tests  605 passed (605)
```

Baseline ile birebir aynı (605/605) — bu plan frontend'e dokunmadı, beklenen buydu.

## Adım 2 — Masaüstü onay kartı: YAPILAMADI

Bu ajan Tauri masaüstü GUI'sini görsel olarak süremiyor (ekran etkileşimi yok). Bu adım
**başarı sayılmıyor** ve kullanıcının elle doğrulaması gerekiyor:

> Fusion masaüstünü kaynaktan başlatıp auto kipte, açıklamasız bir stdio MCP aracı
> (`python -m fusion_cli.mcp_bridge.server <klasör>`) çağıran bir istek gönderin.
> Beklenen: ilk çağrıda onay kartı görünmeli; "oturum boyunca" seçilince ikinci çağrı
> sorulmamalı.

Bunun yerine, GUI'siz ve **hiçbir LLM çağrısı olmadan**, gerçek bir alt-süreç ve gerçek
onay motoru üzerinden eşdeğer kanıt üretildi (aşağıda).

### Gerçek entegrasyon script'i ve çıktısı

Script `tests/test_mcp.py::_server_config` deseniyle Fusion'ın KENDİ MCP sunucusunu
`sys.executable -m fusion_cli.mcp_bridge.server <tmp>` ile gerçek bir stdio alt-süreç
olarak başlatıyor, `McpClient.register_into` ile kayıt defterine ekliyor, `build_policy
(ApprovalMode.AUTO, RecordingPrompter)` kurup `fusion__list_dir` aracı için `decide
(build_request(...))`'i iki kez çağırıyor ve son olarak `registry.execute` ile aracı
gerçekten koşturuyor. Script depoya dahil değil, yalnız scratch dizininde tutuldu.

Komut ve gerçek çıktı (`.venv/bin/python` ile):

```
$ .venv/bin/python task4_integration.py
1) Kayıtlı araç sayısı: 15
   - fusion__browser_close: effect=ToolEffect.REMOTE_WRITE
   - fusion__browser_open: effect=ToolEffect.REMOTE_WRITE
   - fusion__browser_read: effect=ToolEffect.REMOTE_WRITE
   - fusion__git: effect=ToolEffect.REMOTE_WRITE
   - fusion__glob: effect=ToolEffect.REMOTE_WRITE
   - fusion__grep_search: effect=ToolEffect.REMOTE_WRITE
   - fusion__list_dir: effect=ToolEffect.REMOTE_WRITE
   - fusion__list_files: effect=ToolEffect.REMOTE_WRITE
   - fusion__read_file: effect=ToolEffect.REMOTE_WRITE
   - fusion__read_url_content: effect=ToolEffect.REMOTE_WRITE
   - fusion__search_code: effect=ToolEffect.REMOTE_WRITE
   - fusion__todo_write: effect=ToolEffect.REMOTE_WRITE
   - fusion__view_file: effect=ToolEffect.REMOTE_WRITE
   - fusion__web_fetch: effect=ToolEffect.REMOTE_WRITE
   - fusion__web_search: effect=ToolEffect.REMOTE_WRITE
2) İlk çağrı için onay kararı:
  [prompter] soruldu #1: araç=fusion__list_dir etki=ToolEffect.REMOTE_WRITE danger=None
   karar=Decision.ALLOW
3) İkinci çağrı için onay kararı (oturum izni beklenir):
   karar=Decision.ALLOW
4) Prompter kaç kez soruldu: 1
5) Aracı gerçekten çalıştır (registry.execute):
   ok=True
   output (ilk 200 karakter)='📄 ornek.txt'
```

**Yorum:** Fusion'ın kendi sunucusundaki araçlar `readOnlyHint`/`destructiveHint`
taşımıyor (MCP SDK varsayılanı), bu yüzden `effect_from_annotations` hepsini
`REMOTE_WRITE` sayıyor — planın öngördüğü tam olarak buydu ("açıklamasız eski sunucular
`REMOTE_WRITE` sayılır"). Auto kipte `fusion__list_dir` ilk çağrıda bir kez soruldu,
"oturum boyunca" (`ApprovalAnswer.SESSION`) cevabıyla oturum izni kazandı, ikinci çağrı
hiç sorulmadan `ALLOW` döndü — beklenen davranış birebir doğrulandı. Araç gerçekten
çalıştırılıp `ornek.txt` dosyasını listeledi (`ok=True`).

Bu, masaüstü onay kartının GÖRSEL doğrulamasının yerini TUTMAZ (kullanıcı hâlâ elle
bakmalı), ama alttaki karar motorunun ve MCP entegrasyonunun uçtan uca, gerçek bir
alt-süreçle ve LLM'siz doğru çalıştığını kanıtlıyor.

## Bilinen sınırlar

- **Masaüstü GUI görsel doğrulaması yapılamadı.** Onay kartının gerçekten göründüğü,
  "oturum boyunca" seçeneğinin UI'da doğru davrandığı kullanıcı tarafından elle
  kontrol edilmeli.
- **Plan kipi salt okunur uzak araçları da hâlâ tamamen engelliyor.** `PlanApproval.
  decide` her zaman `Decision.BLOCKED` döndürüyor; `REMOTE_READ` etkisi yalnızca
  `auto`/`security` kiplerinde sormama/sorma farkı yaratıyor, plan kipinde hiçbir
  etki sınıfı ayrıcalık kazanmıyor. Bu, planın "Görev 4 dışı" bıraktığı ve sıradaki
  plana (madde 3, aşağıda) devredilen bir sınır.
- **UI'da etki rozeti yok.** Kullanıcı bir aracın `REMOTE_READ`/`REMOTE_WRITE`/
  `REMOTE_DESTRUCTIVE` olduğunu onay kartında göremiyor; yalnız "sorulup sorulmadığı"
  davranışsal olarak farklılaşıyor. ConnectorManifest/capability kataloğu planına
  (aşağıda madde 3) bırakıldı.
- **`ruff format --check .` sürüklenmesi:** Bu görevin dokunmadığı 24 dosyada biçim
  sürüklenmesi var (plan `.md` dosyaları dahil, `src/`'de 8, `tests/`'de 7 Python
  dosyası). Bu plan hiçbirine dokunmadı; sürüklenme bu plandan önce vardı ve kapsam
  dışı bırakıldı. (Not: Görev 0 taslağında bu sayı 18 olarak tahmin edilmişti; bu
  raporun yazıldığı anda gerçek sayı 24'tür — fark muhtemelen aradaki commit'lerde
  dokunulan/eklenen bazı dosyaların ruff biçimiyle tam örtüşmemesinden geliyor, ancak
  bu görevin commit'i format sürüklenmesine dokunmuyor.)

- **Etkileşimsiz koşularda açıklamasız uzak araçlar reddedilir (bilinçli).** TTY
  olmayan ortamda (`fusion run` pipe ile, CI) `ConsolePrompter.confirm` boş cevabı
  onay saymaz ve `False` döndürür. Bu yüzden `readOnlyHint` taşımayan uzak MCP
  araçları (ör. `godot__*`) auto kipte `DENIED` olur. Bu kasıtlıdır: gözetimsiz koşu
  uzak sistemde yazma yapmamalı. Eval koşucusu (`evals/agent_runner.py::_EvalApproval`)
  kendi politikasını kullandığı için etkilenmez. Masaüstünde `/goal` koşusu böyle bir
  çağrıda onay kartında duraklar ve kullanıcının cevabını bekler.
- **Kayıtlı ortam değişkeni eksik stdio sunucusu artık bağlanmaz.** `env_names`
  içindeki bir değişken bulunamazsa `resolve_stdio_env` açık bir hata verir
  ("MCP ortam değişkeni bulunamadı: …") ve sunucu başlatılmaz; eskiden sunucu o
  değişken olmadan başlıyor ve sorun ilk araç çağrısında belirsiz bir hata olarak
  görünüyordu.

## Son inceleme düzeltmeleri

Son incelemede bulunan iki açık, hatayı gösteren testlerle (önce KIRMIZI) kapatıldı:

1. `f449534` — `fix(mcp): barındırmalı bağlantı araçları da uzak etkiyle kaydedilsin`
   (KRİTİK). `HostedConnectorClient.register_into` araçları `effect` vermeden
   kaydediyordu; `MetaAds__update_budget` gibi araçlar `ToolEffect.LOCAL` sayılıp auto
   kipte sorulmadan çalışıyordu. Keşif cevabı modelin yazdığı metin olduğundan MCP
   açıklaması taşınmaz ve doğrulanamaz; bu yüzden açıklamasız varsayılan
   `REMOTE_WRITE` uygulanıyor. Testler: `tests/test_hosted_relay.py` (araç auto kipte
   soruluyor) ve `tests/test_mcp.py::test_hicbir_uzak_arac_yerel_etkiyle_kaydedilmez`
   (stdio/HTTP ve barındırmalı kayıt yollarından hiçbir uzak araç `LOCAL` değil).
2. `b36a585` — `fix(onay): oturum izni tur değişince unutulmasın` (ÖNEMLİ).
   `build_policy` her kullanıcı turunda yeniden çağrıldığı için "oturum boyunca" izni
   yalnız o tur yaşıyordu. İzin kümesi `engines/agent/approval.py::ApprovalMemory`
   nesnesine taşındı; sahibi sohbet durumu `ReplState.approval_memory`'dir ve REPL
   (`cli/repl/loop.py`), TUI (`cli/repl/tui_loop.py`) ile masaüstü
   (`appserver/session.py`, süreç başına tek sohbet) her turda aynı nesneyi
   `run_agent_task(approval_memory=...)`/`build_policy` ile geçiriyor. Tek seferlik
   `fusion run` taze hafıza alır. Yıkıcı (`danger` dolu) çağrılar hiçbir zaman
   hatırlanmaz. Testler: `tests/test_repl.py`, `tests/test_appserver_session.py`
   (iki ayrı turda aynı uzak yazma aracı → tek soru), `tests/test_tui_loop.py`,
   `tests/test_agent_approval.py` (ortak hafıza; yıkıcı çağrı iki kez sorulur).

Tam kapı (bu düzeltmelerden sonra): `ruff check .` temiz, `mypy` temiz (331 dosya), `pytest` 3845 test — 3841 passed, 4 skipped, 0 failed, 0 error (önceki rapora göre +7 yeni test). Frontend değişmedi, `npm test` çalıştırılmadı.

## Kapı özeti

| Kapı | Sonuç |
|---|---|
| ruff check | Yeşil |
| mypy | Yeşil (331 dosya) |
| pytest | Yeşil (3834 passed, 4 skipped, 0 failed — baseline'a göre +18 passed) |
| frontend (vitest) | Yeşil (605/605, baseline ile aynı) |
| masaüstü GUI onay kartı | Yapılamadı — kullanıcı elle doğrulamalı |

## Sıradaki plan (bu planın kapsamı dışında kalanlar)

Plan belgesindeki sıra korunur; her biri ayrı plan ve ayrı onay ister:

1. **DomainAdapter v2 (belge Faz 1):** `adapter_for`'u üretime bağlama, altı Godot
   kontrolünü adaptör kaydına taşıma, kabul ölçütlerini planlayıcıya verme,
   `plan_coverage`'daki oyun teslimlerini alana taşıma, "motor Godot'a bağımlı değil"
   mimari testi.
2. **Composer'da gerçek model ve düşünme seçimi (belge Faz 3):** rol yerine model
   listesi, açık seçimin yetkili olması, desteklenen düşünme seviyeleri, web modeli
   seçimi ve model bazlı araç ölçümü.
3. **ConnectorManifest/capability kataloğu (belge Faz 2 devamı):** backend
   manifestlerinden gelen bağlantı kataloğu, UI'da etki/risk rozeti, plan kipinde
   salt okunur uzak araçlar.
4. Async job + artifact omurgası, Fusion Browser eklentisi, Meshy/Blender/Godot,
   Higgsfield, WordPress/Novamira, reklam ve araştırma fazları.

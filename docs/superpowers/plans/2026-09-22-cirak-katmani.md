# Faz 3 — Çırak Katmanı: Uygulama Planı

> Bu doküman KOD YAZMADAN, yalnızca kod okunarak hazırlanmıştır. `docs/superpowers/plans/2026-09-18-tek-ajan-dongusu.md` ile aynı biçimi izler; görev görev uygulanır. Önerilen beceri `superpowers:subagent-driven-development`.

**Onaylanan kararlar (22 Eylül, §6):** (1) Kullanıcının mevcut `chatgpt_web/strict` seçimi SESSİZCE değiştirilmez; bir sonraki açılışta tek seferlik "ücretsiz çırağa geçmek ister misin?" bildirimi + panelde kalıcı buton. (2) `apprentice_active` `providers/capabilities.py`'ye konur. (3) Ölçümde vision destekleyen model çıkmazsa G1 ve G3 tek commit'te birleşir. (4) CTA metnini uygulayan ajan yazar; ton bilgilendirici olur, web modelini kötülemez.

**Düzeltme:** Proje bir git deposudur (planlayıcı ajanın kabuğu `git`i göremedi). Dal `fusion-runtime-hardening-20260827-022831`, commit kuralları CLAUDE.md'deki gibi geçerlidir.

**Kaynak:** 17 Eylül denetimi (`docs/superpowers/plans/2026-09-17-claude-paritesi.md`, "Faz 3" ve "Mimari yön" bölümleri — dosyada ayrı bir "Mimari kararı" başlığı YOK; mimari yön dokümanın girişinde tanımlı: Öğretmen–Çırak, çırak = ücretsiz API modelleri). Sonuç raporu: `docs/superpowers/reports/2026-09-21-claude-paritesi-faz1-faz2-sonuc.md` ("Faz 3-7 yapılmadı"). Kod 22 Eylül 2026'da okundu. Bu proje **git deposu değil** (`git status` çalışmıyor); bu yüzden HEAD/branch bilgisi verilemiyor, dosya durumu doğrudan diskten okundu.

**Bulgular:** C5 (araç işleri web modelinde), C6 (model zinciri/hız sınırı yönetimi), C9 (kurulumda ücretsiz katman birinci sınıf olmalı), C10 (toplu sayma/filtreleme çırakta kodla yapılmalı), C4 (görsel görevde model hiç çağrılmadan "görsel desteği yok" reddi).

---

## 1. Mevcut durum haritası

### 1.1 Çırak zaten var — ama kullanıcı onu terk etmiş

`src/fusion_cli/config/defaults.yaml` içindeki **paketin gömülü varsayılanı** zaten bir API çırağıdır:

```yaml
agent:
  model: nvidia_nim/nvidia/nemotron-3-super-120b-a12b
  fallback:
    - nvidia_nim/openai/gpt-oss-120b
    - openrouter/nvidia/nemotron-3-super-120b-a12b:free
    - openrouter/openai/gpt-oss-20b:free
```

Beş kademe (`tiers: low/medium/high/ultra/premium`) hepsi NVIDIA NIM + OpenRouter ücretsiz modellerden kurulu; `ultra` kademesi zaten `nemotron-3-ultra-550b-a55b` içeriyor — denetimde ölçülen modellerden biri.

Ancak **bu makinedeki gerçek kullanıcı yapılandırması** (`~/.config/fusion-cli/config.yaml` — depo `.env`'i değil, kullanıcı config dosyası; okundu) şunu gösteriyor:

```yaml
agent:
  name: secilen
  model: chatgpt_web/main/auto
  tags: [strict]
```

`tags: [strict]` → `ModelSpec.strict = True`. Bu, `config/model_select.py::apply_single_model` ile `/development` komutundan kullanıcının kendi seçimiyle geldi (kod: "Kullanıcıya görünen ad; `/development` açıkça TEK model seçtirir"). `strict=True` olduğunda `select_agent_spec` (`config/model_select.py:26-42`) `task_model_map`'i tamamen atlar ve HER turu doğrudan bu web modeliyle çalıştırır — C5'in birebir kaynağı budur. **Bu bir varsayılan davranış hatası değil, kullanıcının geçmişte bilerek yaptığı ama artık geri dönemediği bir seçim.** Sistemde "çırağa dön" diye tek adımlı bir yol yok.

### 1.2 Model zinciri ve hız sınırı — büyük kısmı zaten var

- `src/fusion_cli/providers/chain.py::FallbackProvider.complete/stream` — sıralı yedek zinciri, `ModelFallbackActivated` olayı yayınlıyor (`_publish_fallback`).
- `src/fusion_cli/providers/circuit.py::CircuitBreakingProvider` — devre açıkken çağrı hiç yapmadan bir sonraki modele geçiyor; `rate_limited` ayrımı `ModelHealth.record`'a taşınıyor (429/403 "geçici arıza" değil "kota" sayılıyor, bkz. `defaults.yaml` `circuit_cooldown_s` yorumu).
- `src/fusion_cli/providers/key_pool.py` + `config/key_pool.py::collect_keys` — sağlayıcı başına BİRDEN ÇOK anahtar (numaralı sonek ya da virgüllü), round-robin + cooldown. Zaten "havuz" mantığı var.
- **Görünürlük zaten UI'ya bağlı:** `ModelFallbackActivated` → `src/fusion_cli/ui/renderer.py`, `src/fusion_cli/cli/repl/work_line.py` (CLI) ve `app/src/protocol/olayMetni.ts:79` (masaüstü app) — hepsi bu olayı gösteriyor.
- **Gerçek eksik:** zincir bugün AYNI modelin farklı sağlayıcılardaki kopyalarını dener (`nemotron-super@NIM → nemotron-super@OpenRouter → gpt-oss-20b@OpenRouter`), denetimde istenen "nemotron-super → nemotron-ultra → qwen gibi FARKLI kademeye yükselen" bir zincir değil. Ayrıca 21 ölçülen modelden sadece 3'ü (nemotron-super, nemotron-ultra, gpt-oss ailesi) yapılandırmada var; qwen gibi diğerleri hiç yok.

### 1.3 Görsel — C4'ün kök nedeni bulundu, fonksiyon seviyesinde

Akış: `engines/agent/loop.py::run_agent` (satır ~366) → `deps.task_requirements = infer_task_requirements(task, has_images=bool(images), ...)` (`providers/capabilities.py:120-147`) → daha sonra `config/model_select.py::select_agent_spec` → `providers/capabilities.py::select_compatible_model` → uyumlu model yoksa **model hiç çağrılmadan** `ConfigError` fırlatır (`select_compatible_model`, satır ~104-110).

`compatibility_issues` şu alanlara bakıyor: `capabilities_for(spec, sessions)` (`providers/capabilities.py:37-76`):
- Tarayıcı tabanlı web oturumu (`transport == "browser"`) → **`images = not browser` → her zaman `False`.**
- Web önekli model (chatgpt_web/gemini_web/…) ama oturum kaydı yoksa → **`images = False`** (sabit, satır 61).
- API modeli → `images = capability.vision or "vision" in spec.tags` (satır 71).

`config/eligibility.py::capability_from_spec` (satır 52-58) `ModelCapability.vision` alanını **hiçbir zaman doldurmuyor** (varsayılan `False`, yalnız `tool_support` ve `reasoning` tag'den türetiliyor). `defaults.yaml`'da hiçbir `agent`/`candidates`/`tiers` girdisinde `vision` tag'i yok — yalnız ayrı, agent-dışı `vision:` rolü var (`nvidia_nim/meta/llama-3.2-11b-vision-instruct`, satır 269-271).

Önemli ayrım: disk üzerindeki bir görseli **inceleme** zaten çözülmüş — `engines/agent/engine_tools.py::_view_image_tool` (satır 243-271) `deps.config.vision` rolünü ayrı çağırıyor, agent'ın kendi modelinin görme yeteneğine ihtiyaç duymuyor. C4'ün gerçek kapsamı, kullanıcının **mesaja doğrudan eklediği görsel** (`run_agent(images=...)` → `Message("user", task, images=images)`, `loop.py:2331`) — bu, seçilen modele multimodal girdi olarak gidiyor ve gerçekten o modelin vision desteklemesini gerektiriyor. Bugün hiçbir çırak modeli bu etiketi taşımadığı için istek her zaman `ConfigError` ile ölüyor.

### 1.4 C10 — toplu sayma/filtreleme

Dosya yükleme özelliği (Faz 4 kapsamı, `plans/2026-09-17-claude-paritesi.md` "Faz 4 madde 2") henüz kodda yok (`grep` boş döndü). Çırağın elinde zaten `run_shell` ve `search_code` araçları var (`tools/builtin.py` satır 155, 196) — yani teknik olarak deterministik sayma/filtreleme bugün de mümkün. Eksik olan **yönlendirme**: `engines/agent/prompts/system.md` içinde "sayma/filtreleme işini modelin gözüyle değil `run_shell`/`search_code` ile yap" talimatı yok; `engines/effects/detect.py::required_effect_for` da böyle bir görevi kanıt gerektiren bir etki olarak işaretlemiyor. Faz 4'te dosya yükleme eklendiğinde bu boşluk doğrudan "web modeline bırakılan sayma" hâline gelir; bu yüzden C10 kuralı **Faz 3'te, öğretmen gelmeden önce** çırağın davranışına kazınmalı.

### 1.5 Kurulum/onboarding

`app/src/onboarding/Onboarding.tsx` "Sağlayıcılar" adımı yalnızca `ProviderSummary[]` (kimlik bilgisi var/yok) gösteriyor; veri `appserver/session.py:428` → `appserver/control.py::provider_catalog_rows` → `providers/registry.py::BUILTIN_PROVIDERS`'tan geliyor. Onboarding’de **hiçbir yerde** "ücretsiz katman varsayılan çırak" diye bir vurgu, CTA veya otomatik seçim yok — yalnızca hangi anahtarların girildiğini listeliyor. `config/readiness.py::evaluate` "agent/hakem/aday çalışır mı" diye üç durumlu bir rapor üretiyor ama bunu onboarding hiç çağırmıyor, ve zaten çalışan bir web modeli varsa (`strict`) her şey "READY" görünür — kullanıcıya "aslında ücretsiz API kullanmıyorsun" diye bir sinyal hiç verilmiyor.

---

## 2. Hedef akış

```
kurulum (onboarding)
  → NIM/OpenRouter anahtarı varsa VEYA hiç yoksa: varsayılan çırak defaults.yaml'daki
    "low" kademe (ücretsiz API). Web oturumu login olsa bile agent rolü SESSİZCE
    web'e kaymaz — yalnız kullanıcı açıkça "/development" ile seçerse strict olur.
  → onboarding "Sağlayıcılar" adımı artık salt anahtar listesi değil, readiness.evaluate()
    sonucunu ve "şu an çırağın X modeli" bilgisini gösterir.

kullanıcı mesajı
  → run_agent
      task_requirements.images=True ise: config.vision VAR mı VE seçilebilir
      candidate'larda gerçek (ölçülmüş) vision tag'i VAR mı? İkisi de yoksa kullanıcıya
      "bu görevi görebilen ücretsiz model yok" denir — ama liste GERÇEKTEN denenmiş olur.
      sayma/filtreleme dili tespit edilirse (`effects/detect.py` genişler) →
      requires_tool_evidence=True; model run_shell/search_code kullanmadan "N tane
      buldum" diyemez, kanıt kapısı reddeder.
  → model zinciri: aynı model + farklı sağlayıcı YERİNE, ölçülmüş bir KADEME
    zinciri (nemotron-super → nemotron-ultra → …) devreye girer; 429/403 alan
    HER adımda ModelFallbackActivated kullanıcıya görünür kalır (bu kısım zaten
    çalışıyor, yalnız zincirin içeriği zenginleşiyor).

Ürün bu fazın SONUNDA hâlâ TEK modelle (çırak) çalışabiliyor — öğretmen protokolü
yok, hiçbir tur ikinci bir modele "danışmıyor".
```

---

## Genel kısıtlar

- `CLAUDE.md`/`RULES.md` bağlayıcı. Bu depoda `.env` okunmaz; yalnızca `~/.config/fusion-cli/config.yaml` (kullanıcı config'i, `.env` değil) okundu ve yukarıda alıntılandı.
- Proje **git deposu değil** — commit/branch komutları burada çalışmaz. Uygulama ajanı gerçek bir git deposunda çalışacaksa (örn. ayrı bir worktree/clone), bu planın commit mesajları oraya taşınır.
- Model kimlikleri uydurulmaz. Bu planda yeni bir model adı YAZILMADI (qwen dahil hiçbiri) — denetimde "qwen gibi" örnek olarak geçiyor ama kodda böyle bir kimlik yok; Görev 1 ve Görev 3 açıkça **canlı ölçüm gerektirir** (ağ erişimi) ve bu ölçüm uygulama sırasında yapılmalı, plan aşamasında tahmin edilmemelidir.
- Kalite kapısı: `ruff check . && mypy && pytest -q` (venv yolları depoya göre değişebilir, `Makefile`'a bakılmalı).
- Faz 4 (öğretmen protokolü) bu fazda YAPILMAZ; hiçbir görev ikinci bir model rolü (öğretmen) eklemez.

## Görev bağımlılıkları ve paralellik

```
G0 (başlangıç durumu, salt okuma)
  ├─ G1 (model zinciri genişletme, C6)         ─┐  defaults.yaml'a
  ├─ G3 (görsel çırak, C4)                     ─┘  İKİSİ DE dokunur → SIRALI
  ├─ G2 (kurulumda birinci sınıf çırak, C5/C9)     — dosya kümesi ayrık, paralel
  └─ G4 (toplu sayma çırakta, C10)                 — dosya kümesi ayrık, paralel
       └─ G5 (gerçek koşu doğrulaması, hepsi bitince)
```

G1 ve G3 aynı dosyayı (`config/defaults.yaml`) değiştirdiği için **paralel alt ajanlara verilmez**; ya sıralı çalıştırılır ya da tek ajana verilir. G2 ve G4 dosya kümesi olarak G1/G3'ten ve birbirinden bağımsızdır, paralel yürütülebilir.

---

### Görev 0: Başlangıç durumu (salt okuma)

**Dosyalar:** yok.

- [ ] `git status` çalışmadığından (repo değil) mevcut dosyaların uygulama öncesi bir kopyasını (`cp -r`) `docs/superpowers/` dışında bir yere almak yerine, en azından `config/defaults.yaml`, `config/eligibility.py`, `providers/capabilities.py`, `engines/agent/prompts/system.md`'nin SHA-256'sını kaydet (ikinci bir ajan aynı anda dokunuyorsa çakışmayı yakalamak için).
- [ ] Kalite kapısını çalıştır, test sayısını kaydet. Kırmızıysa DUR.
- [ ] Kullanıcıya §6'daki açık kararları sor (özellikle Görev 2'nin geri dönüş davranışı — kullanıcının şu an aktif `chatgpt_web` seçimini SESSİZCE değiştirmek istenmiyor, bkz. §6.1).

---

### Görev 1: Model zinciri — ölçülmüş kademe geçişi ve zengin fallback (C6)

**Dosyalar (sahiplik):**
- `src/fusion_cli/config/defaults.yaml` (yalnız `agent:` ve `tiers[].agent`/`judge`/`candidates` fallback listeleri — **G3 ile paylaşılır, sıralı çalış**)
- `src/fusion_cli/core/events.py` (yalnız `ModelFallbackActivated` alan eklenmesi gerekirse — örn. "chain_step")
- Yeni: `docs/BACKLOG.md`'ye eklenecek not (eğer 21 modelin tamamı canlı ölçümde doğrulanamazsa hangileri BACKLOG'a kalır)

**Bu görevin dokunmadığı yerler:** `providers/chain.py` mantığı (sıralı-yarıştırmasız davranış korunur; RULES "aynı işi yapan ikinci bir yol açılmaz"), `providers/circuit.py`, `providers/key_pool.py` (zaten doğru çalışıyor).

**Önce yazılacak başarısız testler:** `tests/test_apprentice_chain.py`
- `test_agent_zinciri_farkli_kademeye_yukselir`: `defaults.yaml`'daki `agent.fallback` listesinde, birincil model 429/403 aldığında **farklı bir aile/kademeye** (yalnız aynı modelin başka sağlayıcı kopyasına değil) geçen en az bir adım bulunmalı. Ölçülen `nemotron-ultra` bu listede yer almalı (test, YAML'ı okuyup zincirde model ADLARININ birbirinden farklı olduğunu doğrular — sağlayıcı önekini değil model gövdesini karşılaştırır).
- `test_zincirdeki_her_model_config_testinden_gecer`: mevcut `test_config.py`'deki "her kademe ücretsizdir" (`:free` sonek/NIM) doğrulaması yeni eklenen modeller için de geçer (regresyon kilidi).
- `test_hiz_sinirinda_zincir_gecisi_bildirim_yayinlar`: `fakes.ScriptedProvider` ile ilk model `is_rate_limited=True` dönünce `ModelFallbackActivated` olayı **doğru `fallback_model` alanıyla** yayınlanır (mevcut davranış; regresyon olarak kilitlenir, C6'nın "kullanıcıya görünür bildirim" şartını kanıtlar).
- `test_ust_uste_iki_model_hiz_sinirina_takilinca_ucuncuye_gecer`: zincirde en az 3 basamak olduğu, ikisi art arda 429 dönse bile üçüncünün denendiği doğrulanır (bugünkü 3-4 basamaklı zincirlerde zaten çalışıyor olmalı; yeni eklenen basamak için tekrar sınanır).

**Uygulama adımları:**
- [ ] **(AĞ GEREKİR)** OpenRouter'ın ücretsiz model listesini (`providers/catalog.py::fetch_openrouter_free`) ve NIM kataloğunu canlı çek; denetimdeki 21 modelden hangilerinin GERÇEKTEN araç çağırdığını ve gecikmesini `nemotron-super`/`nemotron-ultra` ölçümüyle aynı yöntemle (gerçek bir `run_agent` turu, gerçek araç çağrısı) doğrula. Sabit uydurma yasağı burada özellikle geçerli: yalnız gerçekten çağrılıp doğru araç çağrısı yapan modeller zincire girer.
- [ ] Ölçülen modelleri `defaults.yaml`'da `agent.fallback` ve ilgili `tiers[].agent.fallback` listelerine, mevcut yorum biçimini koruyarak (ölçüm tarihi + gerekçe) ekle. `low` kademesi zaten `nemotron-super`; zincire `nemotron-ultra`'yı (ölçülmüş: 1.5 sn, doğru araç çağrısı — bu rapor tarafından zaten doğrulanmış) ekle.
- [ ] Hız-sınırlı üç modelin (429/403 görülenler) davranışını `circuit_cooldown_s`/`retry_delays_s` ile uyumlu bırak; yeni bir sabit UYDURMA, mevcut `defaults.yaml` yorumundaki gerekçelendirme biçimini kullan.
- [ ] Ölçülemeyen/erişilemeyen modelleri zincire EKLEME; `docs/BACKLOG.md`'ye "ölçülemedi, tarih X" notu düş (RULES "Ölü Kod" ve "sabitler uydurulmaz" ilkesiyle tutarlı).

**Kaldırılacak / değişecek testler:**
- `test_config.py` içindeki zincir uzunluğu/sıra varsayan testler (varsa) yeni zincire göre güncellenir; **silinmez**, gerekçe: davranış aynı, yalnız zincir zenginleşiyor.

**Risk:**
- Ölçüm anında bazı modeller kota/servis dışı olabilir (NIM/OpenRouter tarafında sık görülen bir durum, kod yorumlarında zaten belgeli). Bu durumda görev **yarım bırakılmaz**; ölçülebilen kadarıyla dar bir zincir eklenir, kalanı BACKLOG'a yazılır.
- `config/defaults.yaml` üzerinde G3 ile çakışma — bu yüzden sıralı.

**Commit:** `feat(cirak): olculmus modellerle zengin yedek zinciri kur`

---

### Görev 2: Kurulumda ücretsiz katman birinci sınıf çırak olsun (C5, C9)

**Dosyalar (sahiplik):**
- `src/fusion_cli/config/model_select.py` (yeni: `reset_to_apprentice_default(config) -> Config` — `strict` kaldırır, `apply_tier(config, "low")` çağırır)
- `src/fusion_cli/config/readiness.py` (yeni: `apprentice_active(config) -> bool` — agent'ın API/local mı yoksa web/browser mı olduğunu `providers/capabilities.py::capabilities_for` ile sorar)
- `src/fusion_cli/appserver/control.py` (yeni alan: `saglayicilar` yanıtına `cirak_aktif`/`onerilen_cirak` eklenir; yeni RPC veya mevcut `kontrol.durum` genişler)
- `app/src/onboarding/types.ts`, `app/src/onboarding/Onboarding.tsx`, `app/src/SessionApplication.tsx` (Sağlayıcılar adımına "varsayılan çırak" satırı ve web-kilitliyse "çırağa dön" düğmesi)
- `src/fusion_cli/cli/repl/macros.py` veya benzeri (CLI tarafı için: `/cirak` ya da mevcut `/development` akışına "varsayılana dön" seçeneği — mevcut komut isimlendirmesi incelenip oraya eklenir, yeni ikinci bir komut ailesi AÇILMAZ)

**Önce yazılacak başarısız testler:** `tests/test_apprentice_default.py`
- `test_strict_web_modelden_cirak_varsayilanina_donus`: `apply_single_model(config, "chatgpt_web/main/auto")` ile strict web'e kilitlenmiş bir config'e `reset_to_apprentice_default` uygulanınca `config.agent.strict is False`, `config.agent.model` `defaults.yaml`'daki `low` kademenin `agent.model`'ine eşit olur.
- `test_cirak_aktif_web_oturumunda_false_doner`: `apprentice_active(config)` — agent modeli `chatgpt_web/...` ya da `transport="browser"` bir web oturumuna eşleniyorsa `False`.
- `test_cirak_aktif_api_modelinde_true_doner`: agent `nvidia_nim/...` ya da `openrouter/...` ise `True`.
- `test_onboarding_saglayici_kartinda_cirak_durumu_gorunur` (appserver): `provider_catalog_rows`/`kontrol.durum` yanıtında yeni alan (örn. `cirak_aktif: bool`, `onerilen_model: str`) var; testte `SecretStore` sahtesiyle iki senaryo (API anahtarı var/yok) sınanır.
- `app/src/onboarding/Onboarding.test.tsx`e eklenecek: `test_saglayicilar_adimi_cirak_durumunu_gosterir` — `providers` listesinde `cirakAktif=false` geldiğinde "Şu an ücretsiz API çırağını kullanmıyorsun" uyarısı render edilir.

**Uygulama adımları:**
- [ ] `readiness.py`'ye `apprentice_active` eklenir; `capabilities_for` importunu **yukarı katmandan** (`providers`) kullanmak `config → providers` bağımlılık yönünü TERSİNE çevirir (RULES katman sınırı: `providers` `config`'e bağımlıdır, tersi değil). Bu yüzden fonksiyon `config/readiness.py`'ye DEĞİL, `providers/capabilities.py`'ye ya da yeni bir `engines`-seviyesi yardımcıya konur; kesin yer katman tablosuna göre kararlaştırılır (bkz. §6.2, kullanıcıya sorulacak).
- [ ] `model_select.py::reset_to_apprentice_default`: `apply_tier(config, "low")` çağırır (RULES "aynı işi yapan ikinci bir yol açılmaz" — mevcut `apply_tier` kullanılır, yeni bir uygulama motoru yazılmaz).
- [ ] `appserver/control.py::provider_catalog_rows` (veya `kontrol.durum` handler'ı) yeni alanı ekler; `SecretStore` sızıntısı olmadığından emin olunur (yalnız bool/model adı döner, anahtar değeri değil).
- [ ] Onboarding "Sağlayıcılar" adımına: (a) `cirak_aktif=false` ise uyarı + "Ücretsiz çırağa dön" butonu (→ `reset_to_apprentice_default` RPC'sini çağırır), (b) `cirak_aktif=true` ise hangi modelin (`onerilen_model`) çalıştığı gösterilir.
- [ ] CLI tarafında eşdeğer bir komut (mevcut `/development` ailesine "varsayılana dön" seçeneği) eklenir; ikinci bir paralel komut ağacı açılmaz.

**Kaldırılacak / değişecek testler:**
- Yok bekleniyor (yeni davranış, eski davranışı bozmuyor — `strict` mekanizması dokunulmadan kalıyor, yalnız geri dönüş yolu ekleniyor).

**Risk:**
- **En hassas görev budur:** kullanıcının şu an aktif `chatgpt_web` seçimini OTOMATİK ve SESSİZCE değiştirmek RULES'un "kullanıcıya sorulmadan varsayılmaz" ilkesini çiğner. Bu yüzden görev yalnızca bir **yol** açar (buton/komut); hiçbir arka plan kodu kullanıcının mevcut config'ini kendiliğinden `reset_to_apprentice_default` ile değiştirmez. Bkz. §6.1.
- Onboarding yalnızca İLK kurulumda çalışır; zaten kurulu kullanıcılar (bu makinedeki gibi) onboarding'i tekrar görmez — bu yüzden CLI/panel tarafında da bir giriş noktası şart.

**Commit:** `feat(kurulum): ucretsiz API cirak varsayilanina donus yolu ekle`

---

### Görev 3: Görsel çırak — ekli görsellerde gerçek yetenek (C4)

**Dosyalar (sahiplik):**
- `src/fusion_cli/core/model_capability.py` (yalnız docstring/yorum netleştirmesi gerekiyorsa)
- `src/fusion_cli/config/eligibility.py` (`_VISION_TAG` sabiti + `capability_from_spec`'te `vision=_VISION_TAG in spec.tags` türetimi eklenir — bugün alan hiç doldurulmuyor)
- `src/fusion_cli/config/defaults.yaml` (yalnız `tags:` alanlarına `vision` eklenmesi — **G1 ile paylaşılır, sıralı çalış**)
- `src/fusion_cli/providers/capabilities.py` (yalnız gerekirse: `images` hesaplamasının `capability.vision` okuduğu satırın doğrulanması; muhtemelen değişmez)

**Önce yazılacak başarısız testler:** `tests/test_vision_capable_apprentice.py`
- `test_vision_tag_capability_vision_alanini_true_yapar`: `ModelSpec(tags=("vision", "agent"))` → `capability_from_spec(spec).vision is True`. Bugün bu test **düşer** (alan hep `False`).
- `test_gorsel_gorevde_vision_tagli_model_secilir`: `TaskRequirements(images=True)` ile `select_compatible_model` çağrıldığında, havuzda `vision` tag'li bir aday varsa `ConfigError` FIRLAMAZ, o aday döner.
- `test_gorsel_gorevde_hic_vision_tagli_model_yoksa_acik_hata_verir`: mevcut davranış (erken, açıklayıcı `ConfigError`) korunur — model hâlâ çağrılmadan durur, ama artık "aslında hiçbir çırak vision desteklemiyor" doğru bir gerekçeyle olur (bugünkü gibi "yapılandırma eksik" değil, "ölçülen hiçbir model bunu desteklemiyor").
- `test_view_image_araci_vision_tagsiz_agentta_da_calisir`: (regresyon) `deps.config.vision` ayrı rol olduğu için, agent modeli `vision` tag'i taşımasa bile `_view_image_tool` diskteki bir görseli hâlâ inceleyebiliyor — C4 çözümünün `view_image` yolunu BOZMADIĞI kilitlenir.

**Uygulama adımları:**
- [ ] `eligibility.py`'ye `_VISION_TAG = "vision"` sabiti ve `capability_from_spec` içine `vision=_VISION_TAG in spec.tags` satırı eklenir (RULES "sabitler merkezi tanımlanır" — mevcut `_NATIVE_TOOL_TAG` deseniyle aynı yerde).
- [ ] **(AĞ GEREKİR)** Mevcut zincirdeki modellerin (nemotron-super, nemotron-ultra, gpt-oss-120b, deepseek-v4-flash, glm-5.2, laguna-xs) OpenRouter/NIM katalog kaydında `architecture.input_modalities` (ya da NIM eşdeğeri) alanı görsel girdi kabul ediyor mu diye canlı sorgulanır; **gerçek bir görsel + soru** ile en az bir model üzerinde uçtan uca doğrulanır (mevcut `vision:` rolü için yapılan "logo ve metin ikonu" ölçümüyle aynı yöntem, `defaults.yaml` satır 260-266'daki gerekçe formatı izlenir).
- [ ] Doğrulanan model(ler)in `tags` listesine `vision` eklenir. **Hiçbiri geçmezse** (mevcut chain'in hiçbiri image-input kabul etmiyorsa), denetimde adı geçen "15/21 görsel okuyan ücretsiz model" havuzundan agent-uyumlu (tool-calling + vision ikisi birden) bir tanesi ölçülüp Görev 1'in zincirine YENİ bir aday olarak eklenir — bu durumda Görev 1 ile ortak bir commit'te birleştirilmesi gerekebilir (§6.3).
- [ ] `ConfigError` mesajı (`select_compatible_model`) güncellenir: "ölçülen modellerin hiçbiri görsel girdi desteklemiyor" gibi somut bir gerekçe verir (RULES "hata mesajları eyleme dönüştürülebilir olur").

**Kaldırılacak / değişecek testler:**
- Yok; mevcut `test_capabilities.py`, `test_provider_capabilities.py`, `test_eligibility.py`'deki `vision=False` varsayan iddialar (varsa) yeni tag mekanizmasına göre güncellenir, silinmez.

**Risk:**
- Ölçüm hiçbir mevcut modeli geçiremezse görev, Görev 1'in zincir genişletmesine bağımlı hâle gelir (aynı `defaults.yaml` bölgesine iki görev dokunur) — bu ihtimal §6.3'te kullanıcıya soruluyor.
- `config/defaults.yaml` üzerinde G1 ile çakışma — sıralı çalış.

**Commit:** `fix(gorsel): olculmus vision etiketiyle cirak dogrudan gorsel gorevi alabilsin`

---

### Görev 4: Toplu sayma/filtreleme çırakta kodla yapılır (C10)

**Dosyalar (sahiplik):**
- `src/fusion_cli/engines/agent/prompts/system.md` (yeni kısa madde: sayma/filtreleme talimatı)
- `src/fusion_cli/engines/effects/detect.py` (`required_effect_for`'a yeni bir desen: sayma/filtreleme dili → `"bulk_count"` gibi bir etki adı, `_MUTATING_EFFECTS`e EKLENMEZ çünkü mutasyon değil, ama `requires_tool_evidence` üretmesi için `execution_policy.py`'nin okuduğu kümeye eklenir)
- `src/fusion_cli/engines/agent/execution_policy.py` (yalnız `required_effect` kümesine yeni etkinin okunması; `_MUTATING_EFFECTS` DEĞİŞMEZ, ayrı bir "kanıt gerektiren ama mutasyon olmayan" küme eklenir ya da `requires_tool_evidence` zaten `required_effect is not None` olduğundan yalnız `detect.py`'deki yeni desen yeterli olabilir — kod okunarak doğrulanacak)

**Önce yazılacak başarısız testler:** `tests/test_bulk_count_evidence.py`
- `test_sayma_dili_kanit_gerektirir`: "bu dosyada kaç tane TODO var, listele" gibi bir görev metninde `required_effect_for(task)` `None` DÖNMEZ (bugün muhtemelen `None` döner, RULES'daki `_MUTATING_EFFECTS` yalnız yazma/push/commit/shell içeriyor); `policy_for(...).requires_tool_evidence is True`.
- `test_sayma_gorevinde_arac_cagrisi_olmadan_sayi_soylenirse_reddedilir`: `fakes.ScriptedProvider` modelin ilk turda araç çağırmadan "37 tane var" dediği bir senaryoda, mevcut kanıt kapısı (`_tool_evidence_satisfied`, `reflexion.tool_evidence_required_note`) devreye girer ve modele "run_shell/search_code ile say" notu döner (yeni davranış DEĞİL, var olan kanıt kapısının bu görev türüne de UYGULANDIĞININ kilitlenmesi).
- `test_sistem_promptu_sayma_talimati_icerir`: `system.md` metninde "say", "filtrele" gibi kelimelerin geçtiği bir cümlede `run_shell` ya da `search_code` önerisi var (basit metin araması, saf test).

**Uygulama adımları:**
- [ ] `detect.py::required_effect_for`e Türkçe sayma/filtreleme dilini (say-, kaç tane, filtrele-, listele- + sayısal bağlam) yakalayan **dar** bir regex eklenir; aşırı geniş eşleşme RULES'un "sabit uydurulmaz" ilkesine aykırı olmaması için mevcut `effects/detect.py`'deki desen yazım biçimi (kelime sınırı, olumsuzlama, örnek yorum) izlenir.
- [ ] `execution_policy.py`: yeni etki adı `requires_tool_evidence=True` üretecek şekilde okunur; `complex_task` (mutasyon) hesaplamasına EKLENMEZ (sayma bir dosya değiştirmiyor, yalnız kanıt istiyor).
- [ ] `system.md`'ye kısa madde: "Bir dosyada satır/eşleşme sayısı ya da filtrelenmiş liste istendiğinde bunu metni okuyup GÖZLE tahmin etme; `run_shell` (`grep -c`, `wc -l`, kısa bir betik) veya `search_code` ile say ve sonucu birebir aktar."

**Kaldırılacak / değişecek testler:**
- `test_effects_detect.py` (var olan dosya) yeni desene göre genişler; mevcut iddialar SİLİNMEZ, yalnız eklenir.

**Risk:**
- Faz 4'te dosya yükleme geldiğinde bu kural web/öğretmen tarafına da taşınmalı; bu görev yalnız çırak tarafını (bugün var olan tek yol) kilitliyor, BACKLOG'a "Faz 4: yüklenen dosyada sayma isteği öğretmene değil önce çırağa yönlendirilsin" notu düşülmeli.
- Regex çok geniş olursa sıradan sohbet sorularını ("kaç yaşındasın" gibi) yanlışlıkla kanıt kapısına sokabilir — testte negatif örnek eklenmeli.

**Commit:** `feat(cirak): toplu sayma ve filtreleme arac kanitina baglansin`

---

### Görev 5: Gerçek koşuyla doğrulama (tüm görevler bitince)

**Dosyalar:** yok (yalnız çalıştırma + gözlem; `evals/` altına senaryo eklenecekse ayrı, küçük bir görev olarak açılır).

- [ ] Kalite kapısı: `ruff check . && mypy && pytest -q`.
- [ ] **(AĞ GEREKİR)** Gerçek bir NIM/OpenRouter anahtarıyla: (a) çırak modelin 429 aldığı bir senaryo simüle edilip (ör. anahtarı kasıtlı geçersiz kılarak ya da hızlı ardışık çağrı ile) zincirin gerçekten farklı bir modele geçtiği ve UI'da göründüğü doğrulanır; (b) gerçek bir görsel ekli mesaj gönderilip artık `ConfigError` ile ölmediği, doğrulanan vision-tag'li modelin cevap verdiği doğrulanır; (c) 200+ satırlık bir dosyada "kaç tane X var" sorusu sorulup modelin `run_shell`/`search_code` çağırdığı (metinden tahmin etmediği) doğrulanır.
- [ ] **(AĞ GEREKMEZ)** Bu makinedeki mevcut `~/.config/fusion-cli/config.yaml` (chatgpt_web/strict) ile onboarding/panel'deki yeni "çırağa dön" yolunun gerçekten `apply_tier("low")` sonucu ürettiği, kullanıcı ONAYLAMADAN hiçbir otomatik değişikliğin olmadığı doğrulanır.

---

## 6. Açık kararlar — kullanıcıya sorulmalı

### 6.1 Mevcut web-kilitli kullanıcılar otomatik mi geçirilsin?

Bu makinede `agent.strict=True` ve `model=chatgpt_web/main/auto`. Görev 2 yalnızca bir **geçiş yolu** (buton/komut) önerir, otomatik geçiş yapmaz. Alternatif: bir sonraki `fusion` başlatmasında tek seferlik bir bildirim ("ücretsiz çırağa geçmek ister misin?") gösterilebilir. Hangisi istenir?

### 6.2 `apprentice_active` fonksiyonu hangi katmanda yaşamalı?

`config` katmanı `providers`'ı import EDEMEZ (RULES katman tablosu: `providers` → `config`'e bağımlı, tersi yasak). `capabilities_for` bugün `providers/capabilities.py`'de. Öneri: `apprentice_active` de `providers/capabilities.py`'ye konur, `appserver` oradan çağırır (`appserver` zaten her katmanı görebilir). Onay istiyorum.

### 6.3 Görsel destekleyen model chain'de yoksa, Görev 1 ile Görev 3 birleşsin mi?

Canlı ölçüm mevcut 6 model içinde vision-input kabul eden hiçbiri çıkmazsa, Görev 3 yeni bir model eklemek zorunda kalır ve bu, Görev 1'in zincir genişletmesiyle aynı `defaults.yaml` bölgesine ikinci bir değişiklik olur. Bu durumda iki görev tek commit'te mi birleştirilsin, yoksa Görev 3 BACKLOG'a mı düşsün (C4'ü bu fazda tam çözmeden)? Ölçüm sonucuna göre karar verilmesini öneririm; şimdiden onay istiyorum.

### 6.4 Onboarding'e "çırağa dön" CTA'sının tam metni ve konumu

Ürün kimliği ("ücretsiz LLM'lerle çalışan" — `CLAUDE.md`) gereği bu mesajın tonu net olmalı ama kullanıcıyı web modelini kullanmaktan caydırıcı/suçlayıcı olmamalı (web modelleri de meşru bir seçenek, yalnız araç işleri için ölçülmüş tavanı düşük). Metni ben mi yazayım yoksa taslağı onaya mı sunayım?

---

## 7. Gerçek koşu doğrulama senaryoları (özet)

| Senaryo | Ağ gerekli mi? | Hangi görev |
|---|---|---|
| Zincirdeki ölçülmüş modellerin gerçekten araç çağırdığının doğrulanması | **Evet** | G1 |
| 429/403'te zincirin farklı modele geçip UI'da görünmesi | **Evet** | G1, G5 |
| Vision-tag'li modelin gerçek görselle doğru cevap vermesi | **Evet** | G3, G5 |
| `view_image` aracının vision-tagsiz agent'ta da çalışmaya devam etmesi | Hayır (fake provider) | G3 |
| Sayma görevinde `run_shell`/`search_code` çağrısının zorunlu olması | Hayır (fake provider) | G4 |
| Onboarding "çırağa dön" yolunun config'i doğru üretmesi | Hayır | G2 |
| Kalite kapısı (`ruff`/`mypy`/`pytest`) | Hayır | Her görev sonu |

---

### Kritik dosyalar (implementasyon için)

- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/config/defaults.yaml`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/config/eligibility.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/providers/capabilities.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/config/model_select.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/engines/agent/loop.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/engines/effects/detect.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/app/src/onboarding/Onboarding.tsx`
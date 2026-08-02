# Migration Planı — Native Universal Runtime Dönüşümü

> Otonom mod, faz sonu kapılı. Her faz sonunda `make check` (ruff + mypy + pytest)
> temiz olmadan commit atılmaz (CLAUDE.md). Kapsam sessizce genişletilmez; büyürse
> faz bölünür. Baseline: **1164 test geçiyor** (2026-08-02).

## İlke

Master prompt Fusion'ı tanımadan yazılmış ve OmniRoute'u referans alıyor. Fusion'ın
mevcut olgun yapıları (kademe sistemi, sıralı fallback, katalog, council, normalize
tipler) **korunur ve genişletilir**; paralel yapı kurulmaz (bkz. ADR 0001).

## Fazlar

### Faz 0 — Baseline + mimari dokümanlar ✅
- Yeşil baseline sabitlendi (`ui/picker.py` sürüm-kayması tip hatası düzeltildi).
- `CURRENT_STATE.md`, `MIGRATION_PLAN.md`, ADR 0001 yazıldı.
- Üretim davranışı değişmedi.

### Faz 1 — Mode + Auto ✅
- `config/profile.py`: profil↔kademe çözümleme; `max` = `premium` alias'ı (tek kaynak).
- `engines/agent/auto_profile.py`: `classify_task` üstünde karmaşıklık sinyalleriyle
  görev→profil seçimi, Türkçe gerekçe. Master prompt §7.2'nin dört örneği çıpa test.
- `/mode` komutu (auto + kademeler) + per-tur auto uygulaması (`loop._apply_auto_profile`).
- 25 yeni test; kapı yeşil (1189 test).
- **Kapsam kararı**: `ReasoningEffort` bu fazdan ÇIKARILDI. "Desteklenmezse no-op"
  doğru çalışması için model başına capability metadata gerekir (Faz 2). Yarım/atılacak
  bir allowlist yazmamak için (RULES.md YAGNI) effort, capability metadata'dan SONRAYA
  alındı (yeni Faz 3). Böylece mode≠effort ayrımı gerçek metadata üstüne kurulur.

### Faz 2 — Capability metadata + eligibility ✅
- `core/model_capability.py`: `ToolSupport` (native/emulated/none/unknown) + `ModelCapability`.
- `config/eligibility.py`: yeteneği model etiketlerinden türetir (agent→native,
  reasoning→reasoning), canlı katalogdan bağlam alır; eşiklerle süzer. Uydurma yok,
  yalnızca bilinen-kötü elenir (gerçekçilik kuralı).
- `defaults.yaml profile_eligibility`: low/medium/high/max eşikleri (koda gömülü değil).
- `/development` katalog listesinde profil rozeti (2b): her model hangi profillere
  uygun, satırda görünür.
- 16 yeni test; kapı yeşil (1205 test).
- **Ertelenen**: hedef-profile göre HARD filtre + "uyumsuzları göster" + red gerekçesi,
  asıl `/profiles` editörüne (§9.4) ait. O editör henüz yok; filtreyi UI'sız yazmak
  spekülatif olurdu (YAGNI). Editörle birlikte gelecek. Pure `is_eligible`/`eligible_profiles`
  altyapısı hazır ve test edilmiş.

### Faz 3 — Reasoning effort (mode ≠ effort) ✅
- `core/reasoning.py`: `ReasoningEffort` (auto/low/medium/high/xhigh/max) + `provider_value`
  (auto→None, xhigh/max→high) + `is_downgraded`.
- Loader'a **generic Enum desteği** (tiplenmiş enum config); `RuntimeConfig.reasoning_effort`
  (`defaults.yaml runtime.reasoning_effort: auto`).
- `CompletionRequest.reasoning_effort` + litellm geçişi (`drop_params` güvenlik ağı).
- Agent turunda **capability-gating** (`_effort_for`): model reasoning desteklemiyorsa
  parametre HİÇ gönderilmez (no-op dürüstçe modelin bilindiği yerde).
- `/effort` komutu (mode'dan bağımsız, oturum-only — onay modu gibi kalıcılaşmaz);
  xhigh/max seçiminde indirgeme kullanıcıya bildirilir.
- 17 yeni test; kapı yeşil (1222 test).
- **Kapsam notu**: effort agent (birincil kodlama) yoluna uygulanır. Utility çağrıları
  (compaction/learning/review/ısıtma) effort ALMAZ — bilinçli (bütçe). Fusion council
  yoluna effort, per-aday gating gerektirdiği için sonraki bir iyileştirmeye bırakıldı.

### Faz 4 — Router sağlamlaştırma ✅
- **Zaten var olan** (dokümante edildi, yeniden kurulmadı): endpoint↔model fallback
  ayrımı (`retrying.py` = aynı model, `chain.py` = sıradaki model), hata-sınıfı bazlı
  tetikleme (`is_permanent_error`/`is_rate_limit_error`/`is_daily_quota_error`).
- **Yeni** (4a): `core/health.py` — `ModelHealth` (circuit breaker: kapalı/açık/yarı-açık +
  cooldown) + EWMA güvenilirlik skoru; `HealthRegistry` (oturum boyunca tek örnek, enjekte,
  zaman `Clock`'tan). Eşikler `defaults.yaml`'dan.
- **Yeni** (4b): `providers/circuit.py` `CircuitBreakingProvider` — devresi açık modeli
  çağırmadan atlar (`FallbackProvider` sıradakine geçer), sonucu sağlığa kaydeder.
  `build_provider(health=...)` opsiyonel; agent path'e threading; `/health` komutu skoru
  ve devre durumunu gösterir.
- Sağlık YALNIZCA sağlıksızı ATLAR, sıralamayı DEĞİŞTİRMEZ: ölçülmüş sıralı zincir kararı
  korunur (chain.py gerekçesi).
- 24 yeni test (11 + 13); kapı yeşil (1246 test).
- **Kapsam notu**: health agent path'e wired; fusion council path'e (effort gibi) sonraki
  bir iyileştirmeye bırakıldı. Route-decision açıklaması bugün olaylarla (hangi model cevap
  verdi) + `/health` ile sağlanıyor; ayrı bir kayıt yapısı YAGNI olurdu.

### Faz 5 — Provider türü framework ✅
- **Gerçekçilik kararı**: LiteLLM ZATEN universal adaptör (OpenAI/Anthropic/Gemini/
  ollama/local hepsi `<provider>/<model>` ile). Paralel canonical adaptör katmanı
  kurmak "ikinci yol" ihlali + devasa atılacak risk olurdu (RULES). LiteLLM yürütücü
  olarak KALIR; Faz 5 tiplenmiş provider METADATA'sı ekler (§22 "framework supported").
- `providers/registry.py`: `ProviderKind` (api_key/oauth/cli_oauth/web_session/
  browser_backed/local/aggregator), `OfficialStatus`, `RiskLevel`, `ProviderDefinition`.
  Built-in registry (openrouter=aggregator, nvidia_nim=api_key, ollama=local); env/önek
  `config.keys`'ten (tek kaynak). `provider_for_model` önekten çözer.
- `/providers` komutu: tür/resmiyet/risk/kurulu-mu. Env erişimi config'te (`environ_snapshot`).
- 10 yeni test; kapı yeşil (1256 test).
- **Ertelenen**: `/providers add` onboarding wizard, web-session credential onboarding'iyle
  birlikte Faz 6'ya. `web_session`/`oauth` türleri tanımlı (enum) ama yürütücüleri Faz 6'da.

### Faz 6 — Tool-support policy + web-session framework ✅ (kısmi, gerçekçi)
- `config/tool_policy.py`: `can_be_mutation_agent` — `NONE` model dosya değiştiren agent
  OLAMAZ (§5.3 güvenlik kuralı), `EMULATED` eval eşiği gelene kadar dışlanır, `NATIVE`/
  `UNKNOWN` yapabilir.
- Capability etiket türetimi genişledi: `no-tools`→NONE, `emulated-tools`→EMULATED
  (açık beyan örtük çıkarımı ezer). Opak/web modelleri dürüstçe işaretlenebilir.
- **Enforcement wired**: `select_agent_spec` araçsız adaya yönlendirilirse varsayılan
  (araç yetenekli) `agent` rolüne düşer — no-tools model yapısal olarak mutation olamaz.
- Web-session sağlayıcıları registry'ye METADATA olarak eklendi (chatgpt_web, gemini_web):
  `web_session` türü, `unofficial_web`, `disabled_by_default`, `implemented=False`;
  `/providers` bunları "framework (adaptör yok)" gösterir.
- 12 yeni test; kapı yeşil (1268 test).
- **Açık gerekçeyle ERTELENEN** (§22): canlı web-scraper yürütücü + şifreli credential
  store + `/providers add` wizard + emulated tool-call eval sistemi. Bir web adaptörü
  kırılgandır, sağlayıcı ToS incelemesi ister, dürüstçe "working" işaretlenemez; CAPTCHA/
  anti-bot aşımı yapılmaz. Framework (türler, risk etiketleri, policy) HAZIR ve test edilmiş.

### Faz 7 — Prompt mimarisi + dokümanlar + parity + smoke
- Katmanlı prompt composer + regression testleri.
- Kullanıcı dokümanları (EXECUTION_PROFILES, MODEL_PICKER, WEB_PROVIDERS, …) ilgili
  fazın koduyla birlikte tamamlanır; `PROVIDER_PARITY_MATRIX.md` gerçeği yansıtır.
- Clean-install smoke testi.

## Kapsam dışı (gerçekçilik kuralı, master prompt §22)

- 290 sağlayıcının tamamı test edilmeden "tam OmniRoute parity" iddia edilmez.
- Web adaptörleri yalnızca gerçekten çalışıp test edilmişse `working` işaretlenir;
  aksi hâlde `framework supported, adapter not yet implemented`.

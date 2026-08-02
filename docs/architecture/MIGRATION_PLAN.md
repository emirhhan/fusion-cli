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

### Faz 1 — Mode/effort ayrımı + Auto
- Kademe → execution profile hizalaması; görünen ad eşlemesi (`premium`→`max`).
- `ReasoningEffort` yeni `core` tipi (auto/low/medium/high/xhigh/max); sağlayıcı
  desteklemezse sessizce en yakına eşlenir, hatalı parametre gönderilmez.
- `/mode` ve `/effort` komutları (`/level`'i genişleterek, ikinci yol açmadan).
- Auto: `classify.py` çıktısını kademe seçimine bağla; karar açıklanabilir olsun.
- Testler: mode/effort bağımsızlığı, desteklenmeyen effort eşlemesi, auto seçim.

### Faz 2 — Model/provider registry + capability metadata
- `core` tipleri: `ModelDefinition`, `ProviderDefinition`, `CapabilitySet`,
  `ModelEndpoint`; `tool_support: native|emulated|none`, context, reasoning.
- Eligibility policy'leri (low/medium/high/max) ve `/model` picker'da filtreleme.
- `Show incompatible` + red gerekçesi. Testler.

### Faz 3 — Router sağlamlaştırma
- Endpoint / model / profile fallback ayrımı; hata-sınıfı bazlı tetikleme tablosu.
- Circuit breaker + cooldown; telemetriden recency-weighted reliability skoru.
- Routing kararı açıklanabilir (route decision kaydı). Testler.

### Faz 4 — Provider türü genişletme (framework)
- `api_key` dışında `oauth` / `local` / `aggregator` birinci sınıf; generic
  OpenAI/Anthropic/Gemini adaptörleri canonical protokol üstünden.
- Provider onboarding wizard (`/providers add`). Testler.

### Faz 5 — Tool-support policy + web-provider framework
- `none` model mutation agent olamaz; `emulated` eval eşiğini geçmeden mutation
  görevine giremez. Emulated tool-call tek canonical format + JSON schema validation.
- `WebProviderAdapter` iskeleti, şifreli credential store (OS keychain/şifreli),
  opt-in + risk etiketi. Credential loglara/prompta/git'e sızmaz. Testler.

### Faz 6 — Prompt mimarisi + dokümanlar + parity + smoke
- Katmanlı prompt composer + regression testleri.
- Kullanıcı dokümanları (EXECUTION_PROFILES, MODEL_PICKER, WEB_PROVIDERS, …) ilgili
  fazın koduyla birlikte tamamlanır; `PROVIDER_PARITY_MATRIX.md` gerçeği yansıtır.
- Clean-install smoke testi.

## Kapsam dışı (gerçekçilik kuralı, master prompt §22)

- 290 sağlayıcının tamamı test edilmeden "tam OmniRoute parity" iddia edilmez.
- Web adaptörleri yalnızca gerçekten çalışıp test edilmişse `working` işaretlenir;
  aksi hâlde `framework supported, adapter not yet implemented`.

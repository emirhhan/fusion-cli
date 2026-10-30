# Mevcut Durum — Fusion CLI Mimarisi

> Bu belge, native universal runtime dönüşümüne başlamadan önce projenin **gerçek**
> durumunu kaydeder. Varsayım değil, dosya okuyarak doğrulanmıştır. Kaynak: `src/fusion_cli`
> (30 Ekim 2026 ölçümü: 566 `.py` dosyası, ≈109 bin satır; ilk yazımda ~18.5 bin satırdı),
> `RULES.md`, `defaults.yaml`.

## Kimlik

Fusion, ücretsiz LLM'lerle çalışan, **iki motorlu** (agent + fusion/council), öz-öğrenen,
terminalde yaşayan bir kodlama asistanıdır. İlk yazımda iki sağlayıcıya bağlıydı (**NVIDIA NIM**
ve **OpenRouter** `:free` modelleri); ücretsiz varsayılan kademe kuralı sürer (`defaults.yaml`
"tiers" notu, `test_config` doğrular). Bugünkü sağlayıcı kümesi için "Sağlayıcı gerçeği"ne bak.

## Katman düzeni (RULES.md "Katman Sınırları")

```
cli → ui → engines → { tools, providers, memory, observability } → config → core
```

- `core` — saf tipler, protokoller, hata sınıfları, sabitler. Üçüncü parti import etmez.
- `config` — `defaults.yaml` tek doğruluk kaynağı; frozen dataclass'lara yüklenir.
- `providers` — LiteLLM adaptörü, katalog, sıralı fallback zinciri, retry, event.
- `memory` — ChromaDB + dersler + kod indeksi; erişilemezse no-op'a düşer.
- `tools` — kayıt defteri + executor + güvenlik + önizleme.
- `observability` — cost/tracing; kapalıyken tam çalışır.
- `engines` — agent döngüsü, fusion/council, playbook, workflow.
- `ui` / `cli` — Rich + prompt_toolkit + Typer; iş mantığı taşımaz.

## Halihazırda var olan, dönüşümün üstüne kuracağı yapılar

| Yetenek | Konum | Not |
|---|---|---|
| Kademe sistemi (low/medium/high/ultra/premium) | `config/defaults.yaml` `tiers:`, `config/models.py:TierSpec`, `config/model_select.py:apply_tier` | Her kademe agent+judge+candidates havuzunu birlikte değiştirir. Tümü ücretsiz. |
| Rol bazlı model seçimi | `TierSpec.agent/judge/candidates` + `task_model_map` | agent/hakem/aday rolleri; görev→model haritası agent turuna bağlı (`model_select.select_agent_spec`). |
| Görev sınıflandırma | `engines/agent/classify.py:TaskKind` | Deterministik, kural tabanlı, model çağrısız. Şu an **kademe seçimine bağlı değil** (yalnız ders kapsamı). |
| Model+provider fallback | `providers/chain.py:FallbackProvider` | SIRALI (yarıştırmalı değil — bilinçli, ölçülmüş karar). |
| Aynı-model retry | `providers/retrying.py` | Geçici arızada aynı modeli `retry_delays_s` ile yeniden dener. |
| Katalog/discovery | `providers/catalog.py` | OpenRouter free + NIM canlı model listesi; ağ hatasında boş liste. |
| Normalize edilmiş sağlayıcı tipi | `core/types.py:ModelResult`, `CompletionRequest` | SDK nesneleri üst katmana sızmaz — canonical protokolün çekirdeği zaten burada. |
| Council/fusion | `engines/fusion/engine.py`, `judge.py` | Çok aday + hakem + sentez. Bütçe/deadline kontrollü. |
| Approval / permission mode | `engines/agent/approval.py`, `config/permissions.py`, REPL `_set_mode` | plan/ask/auto benzeri onay modları. |
| Verification / reflexion / review / learning | `engines/agent/*` | Completion gate, öz-denetim, ders çıkarımı. |
| Bellek + ders + kod indeksi | `memory/*` | ChromaDB, hibrit arama, ders skorlama. |
| REPL komutları | `cli/repl/commands.py` | `/model`, `/level`, `/provider`, `/development`, mode. |

## Sağlayıcı gerçeği

- 30 Ekim 2026 ölçümü: `providers/registry.py` **48** tanım kayıtlı — 44 API anahtarlı/yerel
  (NIM, OpenRouter, OpenAI, Anthropic, Gemini, Ollama, LM Studio, hosted_vllm vb.) ve 4 tarayıcı
  tabanlı web sağlayıcısı (`chatgpt_web`, `gemini_web`, `claude_web`, `copilot_web`; resmî
  olmayan, `terms_review_required`). Ücretsiz varsayılan: NIM ve OpenRouter `:free`.
- Tek doğruluk kaynağı `providers/registry.py`; bu belge sayı tutmaz, yukarıdaki ölçüm tarihlidir.
- Yerel LLM yolu artık var (Ollama, LM Studio, hosted_vllm); gömme için `embedding.provider: local`
  (ChromaDB ONNX) sürer.

## Boşluklar (dönüşümün gerçekten ekleyeceği)

1. **Auto profil** — görevi sınıflandırıp kademe seçen otomatik mod (parça var, bağlanmamış).
2. **Reasoning effort** — mode'dan ayrı, desteklenmezse no-op eşlenen effort kavramı.
3. **Capability metadata** — model başına tool_support (native/emulated/none), context, reasoning.
4. **Eligibility filtreleme** — picker'ın kademeye uygun modelleri süzmesi.
5. **Router sağlamlığı** — circuit breaker, cooldown, telemetriden reliability skoru.
6. **Provider türleri** — api_key dışında oauth/local/web-session/aggregator birinci sınıf.
7. **Web-session framework** — şifreli credential store, opt-in/risk etiketi, emulated tool.
8. **Katmanlı prompt composer** — bugün prompt'lar `engines/agent/prompts/*`.

## Kalite kapısı

`make check` = `ruff check/format --check` + `mypy` + `pytest` (30 Ekim 2026: 669 test dosyası;
ilk yazımda 68).
RULES.md: üçü temiz olmadan commit yok.

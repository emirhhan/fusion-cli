# Sağlayıcı Parity Matrisi

> Gerçeği yansıtır (master prompt §22). Çalışmayan bir sağlayıcı `working` işaretlenmez.
> "290 sağlayıcı parity" iddiası YOKTUR; mimari yeni sağlayıcı eklemeyi kolaylaştırır.

## Durum kodları

- **working** — gerçekten çalışıyor ve test edilmiş.
- **framework** — tür/metadata tanımlı, yürütücü (adaptör) henüz yok.
- **experimental** — native adaptör var ve yapısal testleri geçiyor; tüketici web UI değişimine bağlı.
- **planned** — tasarımda var, tanımı henüz yok.

## Matris

| Sağlayıcı | Kind | Auth | Stream | Tools | Vision | Durum | Kaynak | Testler | Risk |
|-----------|------|------|--------|-------|--------|-------|--------|---------|------|
| OpenRouter | aggregator | api_key | ✅ | native* | model'e bağlı | **working** | LiteLLM | ✅ | normal |
| NVIDIA NIM | api_key | api_key | ✅ | native* | model'e bağlı | **working** | LiteLLM | ✅ | normal |
| OpenAI (resmî) | api_key | OPENAI_API_KEY | ✅ | native* | model'e bağlı | **working** | LiteLLM | ✅ | normal |
| Google Gemini (resmî) | api_key | GEMINI_API_KEY | ✅ | native* | model'e bağlı | **working** | LiteLLM | ✅ | normal |
| Anthropic (resmî) | api_key | ANTHROPIC_API_KEY | ✅ | native* | model'e bağlı | **working** | LiteLLM | ✅ | normal |
| Ollama (yerel) | local | yok | ✅ | native* | model'e bağlı | **framework** | LiteLLM | kısmi | normal |
| Generic OpenAI-uyumlu | api_key/local | değişken | ✅ | native* | değişken | **framework** | LiteLLM | — | normal |
| ChatGPT Web | browser_backed | izole profil/Cookie | pseudo | emulated | — | **experimental** | native Playwright | unit + panel | terms_review_required |
| Claude Web | browser_backed | izole profil/Cookie | pseudo | emulated | — | **experimental** | native Playwright | unit + panel | terms_review_required |
| Gemini Web | browser_backed | izole profil/Cookie | pseudo | emulated | — | **experimental** | native Playwright | unit + panel | terms_review_required |
| Copilot Web | browser_backed | izole profil/Cookie | pseudo | emulated | — | **experimental** | native Playwright | unit + panel | terms_review_required |

\* Araç desteği model başına türetilir (`agent` etiketi → native, `no-tools` → none).
Sağlayıcı seviyesinde varsayılan değildir; bkz. [TOOL_SUPPORT_LEVELS](../TOOL_SUPPORT_LEVELS.md).

## Yürütücü

API/yerel sağlayıcılar **LiteLLM** üzerinden gider. Tüketici web abonelikleri ise
Fusion'ın kendi `WebProviderAdapter` + native Playwright transport'undan geçer; ikinci
bir router/sidecar uygulaması yoktur. Her iki yol da aynı canonical `LlmProvider`,
fallback, retry, circuit breaker ve tool-runtime sözleşmesinde birleşir.

## Yeni sağlayıcı nasıl eklenir

1. `providers/registry.py`'ye bir `ProviderDefinition` ekle (id, kind, auth_env, önek).
2. API-uyumlu sağlayıcıysa LiteLLM zaten çalıştırır — başka kod gerekmez.
3. Web-session/OAuth gibi LiteLLM'in bilmediği bir türse native transport yaz;
   `providers/web_browser.py` browser-backed örneğidir.
4. Testini ekle.

Agent kernel ya da router kodu değişmez.

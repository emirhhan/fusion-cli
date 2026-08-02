# Sağlayıcı Parity Matrisi

> Gerçeği yansıtır (master prompt §22). Çalışmayan bir sağlayıcı `working` işaretlenmez.
> "290 sağlayıcı parity" iddiası YOKTUR; mimari yeni sağlayıcı eklemeyi kolaylaştırır.

## Durum kodları

- **working** — gerçekten çalışıyor ve test edilmiş.
- **framework** — tür/metadata tanımlı, yürütücü (adaptör) henüz yok.
- **planned** — tasarımda var, tanımı henüz yok.

## Matris

| Sağlayıcı | Kind | Auth | Stream | Tools | Vision | Durum | Kaynak | Testler | Risk |
|-----------|------|------|--------|-------|--------|-------|--------|---------|------|
| OpenRouter | aggregator | api_key | ✅ | native* | model'e bağlı | **working** | LiteLLM | ✅ | normal |
| NVIDIA NIM | api_key | api_key | ✅ | native* | model'e bağlı | **working** | LiteLLM | ✅ | normal |
| Ollama (yerel) | local | yok | ✅ | native* | model'e bağlı | **framework** | LiteLLM | kısmi | normal |
| Generic OpenAI-uyumlu | api_key/local | değişken | ✅ | native* | değişken | **framework** | LiteLLM | — | normal |
| ChatGPT Web | web_session | web-session | — | none | — | **framework** | — | metadata | disabled_by_default |
| Gemini Web | web_session | web-session | — | none | — | **framework** | — | metadata | disabled_by_default |

\* Araç desteği model başına türetilir (`agent` etiketi → native, `no-tools` → none).
Sağlayıcı seviyesinde varsayılan değildir; bkz. [TOOL_SUPPORT_LEVELS](../TOOL_SUPPORT_LEVELS.md).

## Yürütücü

Çalışan tüm sağlayıcılar **LiteLLM** üzerinden gider (universal adaptör: OpenAI/
Anthropic/Gemini/ollama/local hepsi `<provider>/<model>` biçimiyle). Fusion paralel
bir canonical adaptör katmanı KURMAZ — bu "ikinci yol" olurdu (RULES). `providers/
registry.py` yalnızca sağlayıcı KİMLİĞİNİ (tür/resmiyet/risk) tutar.

## Yeni sağlayıcı nasıl eklenir

1. `providers/registry.py`'ye bir `ProviderDefinition` ekle (id, kind, auth_env, önek).
2. API-uyumlu sağlayıcıysa LiteLLM zaten çalıştırır — başka kod gerekmez.
3. Web-session/OAuth gibi LiteLLM'in bilmediği bir türse ayrı bir yürütücü yaz
   (henüz örneği yok) ve `implemented=True` yap.
4. Testini ekle.

Agent kernel ya da router kodu değişmez.

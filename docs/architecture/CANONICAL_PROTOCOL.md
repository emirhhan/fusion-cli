# Canonical Protokol

## Durum: ZATEN VAR — çekirdek tiplerdir

Master prompt ayrı bir `CanonicalRequest`/`CanonicalResponse`/`CanonicalStreamEvent`
tip ailesi önerir. Fusion'da bu katman **zaten mevcuttur** ve `core/types.py` içindedir:

| Canonical rol | Fusion tipi |
|---------------|-------------|
| İstek | `CompletionRequest` (messages, temperature, max_tokens, tools, reasoning_effort) |
| Mesaj | `Message` (role, content, tool_calls, images, …) |
| Araç çağrısı | `ToolCall` (id, name, arguments) |
| Sonuç | `ModelResult` (text, tool_calls, usage, reasoning, ok, error, …) |
| Kullanım | `TokenUsage` |
| Akış olayı | `StreamItem` = `TextChunk` \| `StreamDone` |

Bu tipler `core` katmanındadır ve **hiçbir üçüncü parti SDK'ya bağımlı değildir**
(RULES: `core` saf kalır). Sağlayıcı SDK nesneleri üst katmanlara **sızmaz**; her
adaptör yanıtı bu tiplere normalize eder.

## Translator'lar (adaptörler)

Paralel bir canonical katman KURULMAZ (ikinci yol olurdu). Bunun yerine her sağlayıcı
adaptörü canonical tiplere çevirir:

- **`providers/litellm_provider.py`** — LiteLLM üstünden OpenAI / Anthropic / Gemini /
  ollama / OpenAI-uyumlu her uç. LiteLLM'in kendisi protokol translator'ıdır; Fusion
  onun çıktısını `ModelResult`/`StreamItem`'a normalize eder (reasoning alanı, usage,
  tool_calls dahil).
- **`providers/web_session.py`** — oturum tabanlı uçları aynı canonical sözleşmeye
  bağlar; emulated araç çağrısını `core.tool_emulation` ile `ToolCall`'a çevirir.

## Neden ayrı bir `Canonical*` ailesi yazılmadı

- Fusion motorları (agent, fusion/council) zaten yalnızca `core.types` görür; sağlayıcı
  biçimi hiçbir yerde iş mantığına sızmaz. İkinci bir tip ailesi eklemek, aynı işi yapan
  paralel bir yol açardı (RULES "aynı işi yapan ikinci yol açılmaz").
- LiteLLM olgun bir universal translator'dır; OpenAI/Anthropic/Gemini protokol
  çevirisini yeniden yazmak devasa ve kırılgan bir kopya olurdu (§22 gerçekçilik).

## Yeni protokol eklemek

LiteLLM'in bilmediği bir protokol (ör. oturum tabanlı özel bir uç) için:
1. `LlmProvider` sözleşmesini uygulayan bir adaptör yaz (`web_session.py` örnektir).
2. Yanıtı `ModelResult`/`StreamItem`'a normalize et.
3. `build_provider` kompozisyonuna ya da doğrudan kullanuma bağla.

Agent kernel ya da fusion motoru değişmez.

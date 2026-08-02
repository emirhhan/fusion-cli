# Web-Session Sağlayıcıları

## Durum: framework + adapter YAZILDI, canlı ticari transport YOK

`providers/web_session.py` oturum tabanlı bir kaynağı Fusion'ın `LlmProvider`
sözleşmesine bağlayan tam bir adaptör sunar (`WebProviderAdapter`): `complete`/`stream`,
hata sınırı (`ok=False`), mevcut yığına (FallbackProvider, circuit breaker) oturur.
Gerçek I/O yapan `transport` **dışarıdan enjekte edilir** — kullanıcının kendi
OpenWebUI/LibreChat/kurumsal ucu ya da test için mock. Araç desteği `NONE` (düz sohbet)
ve `EMULATED` (talimat enjekte + `ToolCall` ayrıştırma) olarak çalışır; uçtan uca test
edilmiştir (`tests/test_web_session.py`).

**Yazılmayan tek şey:** belirli bir ticari tüketici web arayüzünü (ChatGPT/Gemini web)
izinsiz otomatikleştiren canlı transport — aşağıdaki güvenlik sınırı gereği. Framework
hazır; böyle bir transport'u kullanıcı kendi yetkisiyle sağlar.

## Tarihsel not: framework öncesi durum

Fusion'ın sağlayıcı sistemi web-session sağlayıcılarını **birinci sınıf tür** olarak
tanır (`ProviderKind.WEB_SESSION`), ancak bunların **çalışan bir yürütücüsü henüz
yoktur**. Bu bilinçli bir gerçekçilik kararıdır (master prompt §22):

- Bir web adaptörü **kırılgandır**: sağlayıcı arayüzü değişince sessizce bozulur.
- Sağlayıcı **kullanım şartlarının** kullanıcı tarafından incelenmesini gerektirir.
- Dürüstçe "working" işaretlenemez.

Bu yüzden `/providers` ekranında web sağlayıcıları **"framework (adaptör yok)"**
olarak, `disabled_by_default` ve `unofficial_web` etiketiyle görünür.

## Tanınan web sağlayıcıları (metadata düzeyi)

| id | Tür | Resmiyet | Risk | Durum |
|----|-----|----------|------|-------|
| `chatgpt_web` | web_session | unofficial_web | disabled_by_default | framework, adaptör yok |
| `gemini_web` | web_session | unofficial_web | disabled_by_default | framework, adaptör yok |

## Yapılmayacaklar (güvenlik sınırları)

Canlı adaptör ileride eklense bile şunlar **yapılmaz**:

- CAPTCHA bypass / anti-bot sistemini aşma
- Kullanıcı izni olmadan tarayıcı cookie okuma
- Hesap kısıtlarını aşma, çoklu sahte hesap
- Sağlayıcı kimliğini yanıltıcı biçimde taklit etme

## Canlı adaptör eklendiğinde gerekecekler

Framework şu türleri/etiketleri zaten tanımlar; canlı adaptör bunların üstüne oturacaktır:

- `ProviderKind.WEB_SESSION` / `BROWSER_BACKED`
- `RiskLevel` (fragile, terms_review_required, disabled_by_default)
- `ToolSupport.NONE`/`EMULATED` + mutation policy (araçsız model mutation agent olamaz)
- **Şifreli credential store — YAZILDI** (`config/credentials.py`): `cryptography.Fernet`
  ile şifreli dosya; ana anahtar `FUSION_SECRET_KEY` ortam değişkeninden gelir (diske/
  git'e girmez). `/providers add` sihirbazı bir sağlayıcı anahtarını (getpass ile,
  ekrana yansımadan) alıp şifreli saklar; başlangıçta ortama uygulanır. Değerler ne
  log'a ne prompt'a ne tool sonucuna girer.
- Opt-in login akışı (canlı web adapter için) — henüz yazılmadı (yukarıdaki sınır).

Credential'lar hiçbir zaman prompt'a, log'a, tool sonucuna ya da git'e girmez.

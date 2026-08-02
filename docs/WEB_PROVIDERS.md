# Web-Session Sağlayıcıları

## Durum: framework hazır, canlı adaptör YOK

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
- Şifreli credential store (OS keychain), opt-in login akışı — **henüz yazılmadı**.

Credential'lar hiçbir zaman prompt'a, log'a, tool sonucuna ya da git'e girmez.

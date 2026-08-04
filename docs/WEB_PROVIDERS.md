# Native Web AI Sağlayıcıları

Fusion, ikinci bir router/sidecar uygulamasına ihtiyaç duymadan kullanıcının kendi
ChatGPT, Claude, Gemini ve Microsoft Copilot web oturumlarını deneysel sağlayıcı
olarak çalıştırabilir.

## Desteklenen sağlayıcılar

| Model öneki | Sağlayıcı | Bağlantı |
|---|---|---|
| `chatgpt_web/<hesap>/auto` | ChatGPT Web Plus/Pro | İzole Playwright profili veya manuel Cookie |
| `claude_web/<hesap>/auto` | Claude Web Pro/Max | İzole Playwright profili veya manuel Cookie |
| `gemini_web/<hesap>/auto` | Gemini Web | İzole Playwright profili önerilir |
| `copilot_web/<hesap>/auto` | Microsoft Copilot Web | İzole Playwright profili önerilir |

Bunlar resmî API entegrasyonu değildir. Tüketici web arayüzleri değiştiğinde seçiciler
güncellenmek zorunda kalabilir. Control Panel'deki **Bağlantıyı kontrol et** düğmesi
boş alan kontrolü değil, gerçek küçük bir model isteği çalıştırır.

## Kurulum

```bash
python -m pip install -e '.[web,gateway]'
python -m playwright install chromium
fusion serve
```

Paneli aç:

```text
http://127.0.0.1:8000/dashboard
```

Aynı bilgisayarda panel ve terminal kullanılıyorsa tünel gerekmez.

## Giriş yöntemleri

### Fusion tarayıcısıyla giriş

Önerilen yöntemdir. Control Panel'de sağlayıcı kartını açıp **Tarayıcıyla giriş yap**
düğmesine bas. Fusion, normal Chrome profilini okumadan sağlayıcı/hesap için ayrı bir
kalıcı profil açar. Girişi ve varsa çok faktörlü doğrulamayı kullanıcı kendisi tamamlar.
Pencere kapatıldıktan sonra oturum profilde kalır.

### Manuel Cookie

Kullanıcı yalnızca kendi hesabındaki bir isteğin tam `Cookie` başlık değerini panele
yapıştırabilir. `Cookie:` öneki eklenmez. Bu değer:

- `config.yaml` içine yazılmaz,
- terminale veya loglara basılmaz,
- çocuk süreçlere environment variable olarak verilmez,
- Fernet ile şifreli Fusion secret store içinde tutulur,
- ana anahtar mümkünse macOS Keychain / sistem anahtarlığında saklanır.

`FUSION_SECRET_KEY` tanımlıysa her zaman Keychain anahtarından önce gelir.

## Fusion tool runtime entegrasyonu

Web modeli dosya sistemine veya shell'e doğrudan erişmez. İstek sırasında Fusion,
izin verilen tool şemasını modele metin protokolü olarak verir. Model şu biçimde bir
çağrı üretebilir:

```xml
<tool_call>{"name":"read_file","arguments":{"path":"README.md"}}</tool_call>
```

Fusion bu çağrıyı mevcut tool policy, approval mode, security sınırı ve rollback
mekanizmalarıyla çalıştırır. Araç sonucu canonical konuşmaya eklenip aynı web modeline
yeni tur olarak gönderilir. Böylece web modeli planlama/karar verme katmanıdır;
dosya okuma, arama, shell ve kod düzenleme Fusion'ın kendi güvenli runtime'ında kalır.

## Streaming ve iptal

Web arayüzleri ortak bir kararlı streaming protokolü sunmadığından Fusion cevabı web
sayfasından tamamlandıktan sonra canonical stream'e aktarır. Ctrl+C, üstteki Fusion
turn cancellation zinciri üzerinden bekleyen browser task'ını iptal eder ve geçici
sayfayı kapatır. Aynı sağlayıcı/hesap üzerinde eşzamanlı iki tur açılmaz.

## Güvenlik sınırı

Fusion şunları yapmaz:

- Normal tarayıcı profilinden sessizce cookie çıkarma,
- CAPTCHA çözme veya anti-bot mekanizmasını aşma,
- fingerprint/stealth taklidi,
- başka hesaba ait oturumu kullanma,
- platform kotalarını veya erişim kontrollerini aşma.

Kullanıcı ilgili hizmetin kullanım şartlarını kendisi değerlendirmelidir. Oturum süresi
dolduğunda panelden yeniden giriş yapılır.

## Sorun giderme

- **Mesaj alanı bulunamadı:** Sağlayıcının web arayüzü değişmiş olabilir; görünür
  tarayıcı modunu açıp giriş durumunu kontrol et.
- **Oturum açık değil:** Sağlayıcı kartından Tarayıcıyla giriş yap akışını yenile.
- **Playwright kurulu değil:** `python -m pip install -e '.[web]'` çalıştır.
- **Browser executable yok:** `python -m playwright install chromium` çalıştır.
- **Cookie kaydedilemiyor:** `keyring` kurulu olmalı veya `FUSION_SECRET_KEY`
  tanımlanmalı.
- **Headless modda çalışmıyor:** Panelden arka plan seçimini kapatıp görünür modda
  doğrula; bazı giriş akışları kullanıcı etkileşimi isteyebilir.

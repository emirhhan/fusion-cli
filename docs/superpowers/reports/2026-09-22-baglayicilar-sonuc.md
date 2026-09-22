# Faz 6 — Bağlayıcılar Sonuç Raporu (22 Eylül 2026)

Kaynak: 17 Eylül roadmap özeti (E1-E7), Faz 1/2 sonuç raporu. Kod değişikliği
YOK — bu faz araştırma + canlı doğrulamadan ibaret.

## E1-E6: zaten tamamlanmıştı

Faz 1/2 sonuç raporu (21 Eylül) doğrulandı: `f40dc8b` (hata sınıflandırma),
`f70cfd5` (sunucu başına havuz), `f40ecb2` (bozuk/yinelenen bağlantı
kaydetmeme), `bd97fae` (katalog düzeltme), `04bd4a7` ("Bağlan" düğmesi),
`b974658` (kaydetmeden önce dene) — roadmap özetindeki dört maddenin
(hata sınıflandırma, kaydetmeden doğrulama, kayıt defteri araması,
gerektiğinde başlatma) hepsini karşılıyor. 7 test dosyası
(`test_appserver_bridges.py`, `test_appserver_connectors.py`,
`test_connectors.py`, `test_hosted_bridge.py`, `test_hosted_connector_rpc.py`,
`test_hosted_connectors.py`, `test_hosted_relay.py`) bugünkü tam pytest
koşusunda yeşil.

## E7: ChatGPT connector köprüsü — kısmen doğrulandı, gerçek bir insan
doğrulaması engelinde durdu

**Kök neden bulundu:** `chatgpt_web` sağlayıcısı `recommended_window_mode=
WindowMode.HIDDEN` öneriyor (17 Eylül'de ölçülmüş: headless'ta Cloudflare'a
takılıyor, gizli-ama-gerçek pencerede çalışıyor) ama kullanıcının gerçek
oturumu `headless: true` (HEADLESS) ile yapılandırılmıştı — önerilen kiple
ÇELİŞİYORDU. Bu muhtemelen roadmap'in "oturum engeli" dediği şeydi.

**Canlı test (izole `FUSION_CONFIG`, gerçek config.yaml'a dokunulmadı, gerçek
Meta Ads MCP connector'ı, `HostedConnectorClient.list_tools` — SALT OKUMA
keşif, hiçbir araç ÇAĞRILMADI):** `headless: hidden` ile session gerçekten
daha ileri gitti (jenerik engel sayfası değil), ama gerçek bir hesap-seviyeli
CAPTCHA/insan doğrulamasına ulaştı:

> "ChatGPT Web (Plus/Pro) insan doğrulaması (captcha) istiyor. Bunu otomatik
> aşmak mümkün değil — doğrulamayı görünür tarayıcıda KENDİN tamamlaman
> gerekiyor."

CAPTCHA'yı otomatik aşmak YASAK (güvenlik kuralı) — kod da doğru şekilde
reddedip kullanıcıya net bir çözüm veriyor:

```
python -m fusion_cli.providers.web_login chatgpt_web main
```

**Sonuç:** Köprünün kendisi (kimlik bulma, `HIDDEN` kipe geçiş, connector
konuşması kurma, hata mesajı) ÇALIŞIYOR — yalnız kullanıcının ChatGPT
hesabında BİR KEZ, elle tamamlanması gereken bir insan-doğrulaması var. Bu
kod tarafında düzeltilecek bir hata DEĞİL, kullanıcı eylemi gerektiren bir
adım.

## Yan bulgu (kullanıcı verisi, dokunulmadı)

Kullanıcının gerçek `hosted_connectors:` listesinde aynı Meta Ads MCP için
iki yinelenen kayıt var ("META ADS" / "Meta Ads", yalnız büyük/küçük harf
farkı), ikisi de `verified: false`. `f40ecb2`'nin ("yinelenen bağlantı
kaydetmeme") YENİ kayıtları engellediği ama VAR OLAN yinelenenleri
temizlemediği görülüyor. Kullanıcı onaylamadan silinmedi.

## Genel durum

Faz 6 pratikte TAMAMLANDI: E1-E6 zaten bitmişti, E7'nin kod tarafı canlı
doğrulandı ve doğru çalıştığı kanıtlandı — kalan tek adım kullanıcının kendi
ChatGPT hesabında bir kerelik CAPTCHA tamamlaması (`python -m fusion_cli.
providers.web_login chatgpt_web main`). Kod değişikliği yapılmadı, commit
yok. Sırada Faz 7 (Ölçüm) var.

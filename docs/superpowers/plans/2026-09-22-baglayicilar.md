# Faz 6 — Bağlayıcılar: Durum ve Kalan Kapsam

> Kaynak denetim dosyası (E1-E7) yine depoda yok; roadmap'in tek satırlık
> özetinden ("Hata sınıflandırma, kaydetmeden doğrulama, kayıt defteri
> araması, gerektiğinde başlatma, ChatGPT connector köprüsünün doğrulanması")
> ve Faz 1/2 sonuç raporundan devam edildi.

## 1. Önemli bulgu: bu fazın büyük kısmı ZATEN BİTMİŞ

Faz 1/2 sonuç raporu (`reports/2026-09-21-claude-paritesi-faz1-faz2-sonuc.md`,
satır 22): **"E1–E6 bağlayıcılar | Hata sınıflandırma, doğrulayarak kaydetme,
havuz, katalog, 'Bağlan' | `f40dc8b`, `f70cfd5`, `f40ecb2`, `bd97fae`,
`04bd4a7`, `b974658`"** — roadmap'in özetindeki DÖRT maddenin (hata
sınıflandırma, kaydetmeden doğrulama, kayıt defteri araması, gerektiğinde
başlatma) hepsi bu commit'lerle zaten karşılanmış:

- `f40dc8b` bağlantı hatalarını sınıflandırıp çözüm önerir
- `f70cfd5` sunucuları ayrı havuzlar (bir sunucunun düzelmeyen hatası diğerini bloklamaz)
- `f40ecb2` bozuk/yinelenen bağlantıyı KAYDETMEZ
- `bd97fae` katalogdaki çalışmayan girdileri düzeltir
- `04bd4a7` giriş gereken bağlantıya "Bağlan" düğmesi (masaüstü)
- `b974658` bağlantıyı KAYDETMEDEN ÖNCE DENER

Kod tabanında da geniş test kapsamı doğrulandı (7 test dosyası):
`test_appserver_bridges.py`, `test_appserver_connectors.py`,
`test_connectors.py`, `test_hosted_bridge.py`, `test_hosted_connector_rpc.py`,
`test_hosted_connectors.py`, `test_hosted_relay.py` — hepsi bugünkü tam
pytest koşusunda YEŞİL.

**Tek gerçekten kalan madde: "ChatGPT connector köprüsünün doğrulanması"
(E7).** Roadmap'in kendi "Açık kalan ölçümler" bölümü bunu zaten işaretlemiş:
*"ChatGPT üzerinden dosya yükleme ve connector köprüsü (oturum engeli
kalkınca)."*

## 2. E7'nin neden bloklandığı — bugün netleşti

Faz 4 Görev 2'de (dosya yükleme) ChatGPT web'de headless Chrome bir
bot-doğrulama ("Bir dakika lütfen…") sayfasında takıldı. O zaman "bilinen bir
sorun, ChatGPT'de denenmedi" diye not edildi. Bugün kodu tekrar okudum:

`providers/web_browser.py:219` — `chatgpt_web` sağlayıcı tanımı AÇIKÇA
`recommended_window_mode=WindowMode.HIDDEN` diyor (gerçek ama ekrandan gizli
pencere), `WindowMode.HEADLESS` (satır 176) DEĞİL — bu tam olarak 17 Eylül'de
ölçülüp belgelenen düzeltme ("ChatGPT görünmez Chrome'da Cloudflare
doğrulamasına takıldı, gizli kipte ilk turda çalıştı").

**Ama kullanıcının GERÇEK oturum yapılandırması** (`~/.config/fusion-cli/
config.yaml`) chatgpt_web için `headless: true` diyor — sağlayıcının kendi
önerisiyle ÇELİŞİYOR. Bu, E7'yi bloke eden "oturum engeli"nin muhtemel
nedenidir: session.headless=true `recommended_window_mode=HIDDEN`'ı EZİYOR.

## 3. Gerçek, iş-kritik veri: kullanıcının gerçek connector'ı

Kullanıcının gerçek config'inde ZATEN bir hosted connector tanımlı:

```yaml
hosted_connectors:
- name: META ADS
  url: https://mcp.facebook.com/ads
  provider: chatgpt_web
  verified: false
- name: Meta Ads
  url: https://mcp.facebook.com/ads
  provider: chatgpt_web
  verified: false
```

İki girdi de `verified: false` — VE birbirinin neredeyse aynısı (yalnız isim
büyük/küçük harf farkı). Bu, `f40ecb2`'nin ("bozuk ya da yinelenen bağlantıyı
kaydetme") kapsamına GİRMESİ gereken ama muhtemelen o düzeltmeden ÖNCE
eklenmiş bir kalıntı olabilir — ya da düzeltme yalnız YENİ kayıtları
engelliyor, var olan yinelenenleri temizlemiyor. Bu proje belleğinde daha
önce not edilmiş: Meta Ads MCP kullanıcının GERÇEK, iş-kritik bir bağlantısı
(motogate/GATE HOLDING reklam hesapları için).

## 4. Kalan iş — kullanıcıya sorulmalı

E7'yi gerçekten doğrulamak şu anlama gelir: (a) `headless: true`'yu
`HIDDEN`'a çevirip gerçek bir ChatGPT web oturumu açmak, (b) gerçek Meta Ads
connector'ı üzerinden gerçek bir MCP aracı çağrısı denemek. Bu, kullanıcının
GERÇEK ChatGPT hesabında görünür bir pencere açacak ve gerçek bir iş aracını
(Meta Ads) tetikleyecek — deneme amaçlı bile olsa gerçek bir API çağrısı
riski taşıyabilir (hangi aracın çağrılacağına bağlı). Ayrıca iki yinelenen
connector kaydını temizlemek (biri silinmeli) kullanıcının verisine
dokunmak demektir.

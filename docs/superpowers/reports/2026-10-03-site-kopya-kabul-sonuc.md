# "Siteye birebir benzeyen e-ticaret" kabul koşuları — sonuç (2–3 Ekim 2026)

Kullanıcının Fusion'a verdiği istek bir TEST olarak alındı ve aynı istek boş bir klasörde,
gerçek ücretsiz modelle (`nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b`, öğretmen Gemini web)
tekrar tekrar koşuldu; her tıkanmanın kök nedeni Fusion'da GENEL bir düzeltmeye çevrildi.
Plan ve koşu tablosu: `docs/superpowers/plans/2026-10-02-calistir-ve-goster.md`.

İstek: "wordpress tabanlı bir website … birebir olarak https://www.sneaksup.com sitesine
benzeyecek görsellerine kadar … her sayfasıyla, her eklentisiyle gerçek çalışan bir e-ticaret".

## Nereden nereye

| | 5. koşu (başlangıç) | 10. koşu |
|---|---|---|
| Süre / araç çağrısı | 20 dk / 44 | 50 dk / 115 (adım sınırına kadar) |
| Öğretmen planı | yok (Gemini kalıp ret, ChatGPT captcha) | 9 adımlı JSON plan + 2 "yapılamayan" (ödeme altyapısı, hosting) |
| Kaynak site ölçümü | yok (15× `browser_open`, tahmin) | `site_design`: 5 sayfa, 120 görsel, 16 font, 2 video, 48 ürün, 14 bölüm |
| WordPress | kurulamadı (MySQL döngüsü) | `start_preview(kind=wordpress, plugins=[woocommerce])` tek çağrıda, SQLite |
| Tema | 0 dosya | 10 dosya: header/footer/front-page/woocommerce şablonları, 12 bölüm sırayla, gerçek kahraman videosu, Inter/Oswald, aynı menü |
| Ürün | 0 | 48 ürün + beden varyasyonu, mağaza/ürün/sepet/ödeme sayfaları 200 |
| Kabul denetimi (`evals`, kullanıcı gözüyle) | — | 12/17 |

10. koşunun açık kalan eksikleri: ürün görselleri kırık (modelin içe aktarma betiği yanlış yol
yazdı; `start_preview` 404'leri adıyla bildirdi ama model adım sınırında düzeltemedi), fiyatlar
"7.499,00 TL" → "$749.900" (yanlış ayrıştırma + para birimi), üst bilgide logo yok.
Bunlar için 11. koşudan önce eklenenler: `urunler.json`'da `fiyat_sayi`/`para_birimi` ve
"para birimini TRY yap" notu; kapanış doğrulaması tarayıcıyla ölçüp 404 kaynakları da
"doğrulanmadı" sayar; `start_preview` kabuk adımından sonra da yeniden çağrılabilir.

**11. koşu** (tüm düzeltmelerle, 253 araç çağrısı, ~70 dk): ürün görselleri düzeltildi (0 kırık),
fiyatlar TL, logo/Oswald üst bilgi, 40 fiyatlı ürün ana sayfada, mağaza 20+ ürün, ödeme formu;
kabul denetimi 14/17. Son adımlarda model `woocommerce.php` şablonunu bozdu ve ürün sayfaları
"Shop" listesi oldu; ana sayfa hatasız olduğu için kapanış kapısı görmedi → `start_preview`
artık sitenin bir ürün sayfasını da ölçüp karşılaştırıyor (`1ac627d`).
**12. koşu**: model "her eklentisiyle" diye Wordfence/Autoptimize/iyzico/PayTR kurdu; SQLite'lı
sitede her `wp` komutu asılı kaldı, koşu durduruldu → asılı kalan wp adımı artık
`--skip-plugins` kaçış kapısını söylüyor (`17d25fc`). Sıradaki koşu bu ikisini sınar.

**13. koşu** (~45 dk): kabul denetimi **15/17** — ürün sayfası başlık/fiyat/galeri/sepete ekle
çalışıyor, sepete ekleme sayacı artıyor, 0 kırık kaynak, ödeme formu var. Kalan: sepet
sayfası içeriği boş geliyor (tema sayfa şablonu), para birimi hâlâ `$` (model `para_birimi`
notunu uygulamadı), ana sayfada ürün şeridi yerine görsel ızgaraları, mağaza kartında ad ve
düğme iki kez (kanca iki kez bağlanmış).

**14. koşu** (~50 dk, para birimi kurulumda uygulanıyor, yinelenen kart uyarısı, düşünme
bütçesi dolunca düşük yoğunluk): kabul denetimi **16/17** — 0 kırık kaynak, 74 fiyatlı ürün ana
sayfada, mağaza 24 ürün, ürün sayfası 3 görsel + fiyat (TL) + sepete ekle, sepete ekleme sayacı
çalışıyor. Ekran görüntüleri yanlış pozitifi gösterdi: sepet ve ödeme adresleri 200 dönüp **ana
sayfayı** render ediyor (temada `page.php` yok, WooCommerce sayfaları öne düşüyor); kabul
denetimi fiyat metnine kandığı için 16/17 saydı, gerçek puan 14/17. Düzeltme: önizleme, izlediği
iç bağlantı ana sayfayla aynı içeriği gösteriyorsa "sayfa şablonu eksik olabilir" der.

**15. koşu**: model ilk tema dosyasında çıktı bütçesinin tamamını düşünmeye harcadı (8k, 16k,
32k token; her biri 80-120 sn), hiç dosya yazamadı → ölçüm: NIM Nemotron `reasoning_effort`'u
tanımıyor ama şablon anahtarı `chat_template_kwargs.enable_thinking=false` tanıyor (aynı header.php
161 sn/4130 token → 29 sn/2973 token, araç çağrısı geçerli). Düzeltme: düşünme bütçesi dolunca
yeniden deneme bu anahtarla yapılır (`CompletionRequest.disable_thinking`).

**16. koşu** (düşünme anahtarıyla, ~55 dk): kabul denetimi **16/17** ve bu kez ekran görüntüleri de
doğruluyor — sepet sayfası gerçek (1 ürün, toplamlar, "Ödemeye git"), ödeme sayfası gerçek form
(fatura adresi; ödeme yöntemi tanımlı değil), 0 kırık kaynak, 44 fiyatlı ürün ana sayfada, mağaza
29 ürün, ürün sayfası tam. Kalan: kahraman bu kez video değil kampanya görseli; kapanış öğretmen
denetimi modelin sepet/favori JS'ini kaynak sitenin canlı API'sine bağladığını yakaladı →
ölçüm örneklerinden satır içi olay kodu çıkarıldı ve kaynak alan adına istek atan sayfa
"KAYNAK SİTEYE İSTEK" diye uyarılıyor. Tur NIM 429 ile kapandı (ücretsiz katman).

## Fusion'da kalıcı olarak değişenler

1. **Öğretmen** — araçsız istek araç çerçevesiz gider; plan isteği `PLAN_FRAME` + çırağın araç
   listesiyle; kalıp ret/süre aşımında aynı hesapta komşu web modeline geçilir ve hatırlanır;
   reddeden öğretmene bir kez daha sorulur; ret öğretmeni tur boyunca kapatmaz; ret kalıbı
   ölçülen Gemini biçimleriyle genişledi; yarım kalan web turunun sekmesi kapatılır.
2. **Çalıştır ve göster** — `start_preview` boş klasörde WordPress kurar (eklenti listesiyle),
   WooCommerce "yakında" sayfasını kapatır, ekran görüntüsünü `.fusion/onizleme.jpg`'ye yazar,
   yüklenemeyen kaynakları adıyla söyler, kaynak site ölçülmüşse **KAYNAKLA FARKLAR** verir.
3. **Site ölçümü** — `site_design` bölüm sırası, ürün kataloğu (yerel görsel, sayısal fiyat,
   para birimi, galeri, seçenekler), logo dosyası, kahraman videoları, görünmeyen yazı ve menü
   dizilişi ölçer; eklenti bağlıysa kullanıcının Chrome'unda çalışır.
4. **Döngü** — görsel okuyamayan modele araç görseli gitmez (`view_image` notu); süre aşımından
   sonra "kısa adım at" notu; API istem katmanında "uzun dosyayı böl"; `Tool.reruns_on_change`;
   başarılı kabuk adımı düşen çağrıları serbest bırakır; dizine yazma denemesi doğru mesaj verir.
5. **Yönlendirme** — adres + benzerlik sözü taşıyan istek önce `site_design`'a gider;
   kapsam notu "bitince kalanı listele" der; kaynak sitenin içeriği yerel çalışma için alınır,
   yayına almadan önce değiştirilmesi gerektiği kullanıcıya söylenir.

## Ölçülen dış sınırlar (Fusion'ın dışı)

- Gemini "3.1 Pro" bu hesapta 2 Ekim akşamı her soruya kalıp ret verdi ya da 180 sn'yi aştı;
  "3.6 Flash" 25 sn'de doğru cevapladı. Fusion artık kendiliğinden Flash'a geçiyor.
- ChatGPT web oturumu insan doğrulaması bekliyor: `fusion web-login chatgpt_web` (kullanıcı işi).
- NIM 21:25–23:30 arasında "Service temporarily overloaded" verdi (9. koşu bu yüzden düştü);
  araç çağrısı parça parça akmıyor, büyük dosya yazan tek çağrı 600 sn sınırına yaklaşıyor.
- Nemotron 3 Ultra görsel okuyamıyor; ekran görüntüsü yerine ölçülmüş metin farkları verilir.

## Nasıl tekrar ölçülür

```bash
mkdir /tmp/kabul && cd /tmp/kabul
FUSION_CONFIG=~/.config/fusion-cli/config.yaml fusion agent "<aynı istek>" --json > kabul.jsonl
```
Sonra siteyi `php -S 127.0.0.1:8770 -t /tmp/kabul` ile açıp kullanıcı gözüyle gez: ana sayfa,
mağaza, ürün sayfası, sepete ekle, sepet, ödeme; `start_preview` çıktısındaki KAYNAKLA FARKLAR
listesinin boşalıp boşalmadığına bak.
